from datetime import datetime, timezone
import enum as py_enum
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import authorize_api_request
from sqlalchemy import and_, delete, func, insert, or_, select, update

from app.db import Base, db_session
from app.models import (
    Correlation, Entity, Finding, InvestigationCheckpoint, Job, JobStatus,
    MembershipRole, OrganizationMembership, Relationship, User, UserRole,
    InvestigationShare, InvestigationComment,
)
from app.repository import Repository
from app.schemas import (
    CorrelationAssessmentRequest,
    CorrelationResponse,
    EntityCreateRequest,
    EntityUpdateRequest,
    EntityFindingAttachRequest,
    EntityResponse,
    ProfileResponse,
    GraphResponse,
    RelationshipCreateRequest,
    RelationshipUpdateRequest,
    ManualNameSearchRequest,
    RelationshipResponse,
    RelationshipAssessmentRequest,
    FindingAssessmentRequest,
    FindingResponse,
    IngestNameRequest,
    InvestigationCreateRequest,
    JobCreatedResponse,
    JobResponse,
)
from app.tasks import process_person_name_job, process_manual_person_name_search


router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize_api_request)])


# Snapshot only data owned by an investigation. Authentication/organization tables
# and the checkpoint table itself are deliberately outside the snapshot boundary.
def _investigation_tables():
    metadata_tables = Base.metadata.tables
    scoped = {"jobs"}
    excluded = {"investigation_checkpoints", "investigation_shares", "investigation_comments", "users", "organizations", "organization_memberships"}
    changed = True
    while changed:
        changed = False
        for table in metadata_tables.values():
            if table.name in scoped or table.name in excluded:
                continue
            if any(fk.column.table.name in scoped for fk in table.foreign_keys):
                scoped.add(table.name)
                changed = True

    ordered = []
    pending = {name for name in scoped if name != "jobs"}
    ordered.append(metadata_tables["jobs"])
    while pending:
        ready = sorted(
            name for name in pending
            if all(
                fk.column.table.name not in scoped
                or fk.column.table.name in {table.name for table in ordered}
                for fk in metadata_tables[name].foreign_keys
            )
        )
        if not ready:
            raise RuntimeError("Could not order investigation tables by foreign-key dependencies")
        ordered.extend(metadata_tables[name] for name in ready)
        pending.difference_update(ready)
    return ordered


def _encode_snapshot_value(value):
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, py_enum.Enum):
        return {"$enum": value.value}
    if isinstance(value, dict):
        return {key: _encode_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_snapshot_value(item) for item in value]
    return value


def _decode_snapshot_value(value, column=None):
    if isinstance(value, dict) and "$datetime" in value:
        return datetime.fromisoformat(value["$datetime"])
    if isinstance(value, dict) and "$enum" in value:
        enum_class = getattr(getattr(column, "type", None), "enum_class", None)
        raw = value["$enum"]
        if enum_class:
            try:
                return enum_class(raw)
            except ValueError:
                return enum_class[raw]
        return raw
    if isinstance(value, dict):
        return {key: _decode_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_snapshot_value(item) for item in value]
    return value


def _collect_investigation_rows(session, job_id):
    tables = _investigation_tables()
    scoped_names = {table.name for table in tables}
    collected = {}
    parent_values = {}
    for table in tables:
        if table.name == "jobs":
            rows = session.execute(
                select(table).where(table.c.id == job_id).order_by(*table.primary_key.columns)
            ).mappings().all()
        else:
            conditions = []
            for fk in table.foreign_keys:
                parent = fk.column.table.name
                if parent not in scoped_names:
                    continue
                values = parent_values.get((parent, fk.column.name), [])
                if values:
                    conditions.append(fk.parent.in_(values))
            rows = (
                session.execute(select(table).where(or_(*conditions)).order_by(*table.primary_key.columns)).mappings().all()
                if conditions else []
            )
        normalized = [dict(row) for row in rows]
        collected[table.name] = normalized
        for row in normalized:
            for column in table.columns:
                parent_values.setdefault((table.name, column.name), []).append(row[column.name])
    return tables, collected


def _make_investigation_snapshot(session, job_id):
    tables, collected = _collect_investigation_rows(session, job_id)
    if not collected.get("jobs"):
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "version": 1,
        "tables": [
            {
                "name": table.name,
                "rows": [
                    {key: _encode_snapshot_value(value) for key, value in row.items()}
                    for row in collected[table.name]
                ],
            }
            for table in tables
        ],
    }


def _normalize_shared_snapshot(snapshot, share, baseline):
    """Translate a collaborator snapshot into the original investigation ID space."""
    metadata_tables = {table.name: table for table in _investigation_tables()}
    reverse_map = {
        table_name: {str(copy_id): str(original_id) for original_id, copy_id in mapping.items()}
        for table_name, mapping in (share.id_map or {}).items()
    }
    baseline_jobs = next((item["rows"] for item in baseline.get("tables", []) if item["name"] == "jobs"), [])
    baseline_job = baseline_jobs[0] if baseline_jobs else {}
    normalized = {"version": snapshot.get("version", 1), "tables": []}
    for item in snapshot.get("tables", []):
        table = metadata_tables.get(item["name"])
        if table is None:
            continue
        rows = []
        pk_names = [column.name for column in table.primary_key.columns]
        for encoded in item.get("rows", []):
            row = dict(encoded)
            for pk in pk_names:
                value = row.get(pk)
                if value is not None:
                    row[pk] = reverse_map.get(table.name, {}).get(str(value), str(value))
            for fk in table.foreign_keys:
                column_name = fk.parent.name
                value = row.get(column_name)
                if value is not None:
                    row[column_name] = reverse_map.get(fk.column.table.name, {}).get(str(value), str(value))
            if table.name == "jobs":
                row["id"] = baseline_job.get("id", share.original_job_id)
                for name in ("owner_user_id", "organization_id"):
                    if name in baseline_job:
                        row[name] = baseline_job[name]
            rows.append(row)
        normalized["tables"].append({"name": item["name"], "rows": rows})
    return normalized


def _review_value(value, limit=350):
    """Keep review payloads readable and bounded even for large evidence fields."""
    if isinstance(value, (dict, list)):
        value = str(value)
    elif value is None:
        return None
    else:
        value = str(value)
    return value if len(value) <= limit else value[:limit] + "…"


def _investigation_snapshot_diff(baseline, current):
    """Return a bounded row-level diff for the proposal review screen."""
    before_tables = {item["name"]: item.get("rows", []) for item in baseline.get("tables", [])}
    after_tables = {item["name"]: item.get("rows", []) for item in current.get("tables", [])}
    table_meta = {table.name: table for table in _investigation_tables()}
    result = []
    for table_name in sorted(set(before_tables) | set(after_tables)):
        table = table_meta.get(table_name)
        if table is None:
            continue
        pk_names = [column.name for column in table.primary_key.columns]
        def indexed(rows):
            return {tuple(str(row.get(key)) for key in pk_names): row for row in rows}
        before = indexed(before_tables.get(table_name, []))
        after = indexed(after_tables.get(table_name, []))
        added_keys = sorted(set(after) - set(before))
        deleted_keys = sorted(set(before) - set(after))
        common = sorted(set(before) & set(after))
        modified = [
            {"id": "/".join(key), "fields": sorted(
                field for field in set(before[key]) | set(after[key])
                if before[key].get(field) != after[key].get(field)
            )}
            for key in common if before[key] != after[key]
        ]
        if added_keys or deleted_keys or modified:
            details = []
            for key in added_keys[:50]:
                details.append({
                    "operation": "added", "id": "/".join(key),
                    "values": {name: _review_value(value) for name, value in after[key].items() if name not in pk_names},
                })
            for key in deleted_keys[:50]:
                details.append({
                    "operation": "deleted", "id": "/".join(key),
                    "values": {name: _review_value(value) for name, value in before[key].items() if name not in pk_names},
                })
            for key in common:
                if before[key] == after[key]:
                    continue
                fields = sorted(field for field in set(before[key]) | set(after[key]) if before[key].get(field) != after[key].get(field))
                details.append({
                    "operation": "modified", "id": "/".join(key), "fields": fields,
                    "values": [
                        {"field": field, "before": _review_value(before[key].get(field)), "after": _review_value(after[key].get(field))}
                        for field in fields[:30]
                    ],
                })
                if sum(1 for item in details if item["operation"] == "modified") >= 50:
                    break
            result.append({
                "table": table_name, "added": len(added_keys),
                "deleted": len(deleted_keys), "modified": len(modified),
                "details": details,
            })
    return result


def _restore_investigation_snapshot(session, job_id, snapshot):
    tables, current = _collect_investigation_rows(session, job_id)
    table_by_name = {table.name: table for table in tables}
    snapshot_rows = {item["name"]: item["rows"] for item in snapshot.get("tables", [])}
    job_table = table_by_name["jobs"]
    baseline_jobs = snapshot_rows.get("jobs", [])
    if not baseline_jobs:
        raise RuntimeError("Checkpoint does not contain the investigation row")

    # Delete current child records in reverse dependency order, but retain the
    # jobs row so references and concurrent readers never observe a missing job.
    for table in reversed(tables):
        if table.name == "jobs":
            continue
        for row in current.get(table.name, []):
            keys = [column == row[column.name] for column in table.primary_key.columns]
            if keys:
                session.execute(delete(table).where(and_(*keys)))

    # Restore the existing job in place, then reinsert its child records in
    # dependency order so all foreign keys point to restored baseline records.
    job_values = {
        column.name: _decode_snapshot_value(baseline_jobs[0][column.name], column)
        for column in job_table.columns
        if column.name in baseline_jobs[0] and column.name != "id"
    }
    session.execute(update(job_table).where(job_table.c.id == job_id).values(**job_values))

    for table in tables:
        if table.name == "jobs":
            continue
        for encoded_row in snapshot_rows.get(table.name, []):
            row = {
                column.name: _decode_snapshot_value(encoded_row[column.name], column)
                for column in table.columns
                if column.name in encoded_row
            }
            session.execute(insert(table).values(**row))


def _lock_job_for_mutation(session, job_id):
    """Serialize every investigation write against checkpoint restoration."""
    exists = session.scalar(
        select(Job.id).where(Job.id == job_id).with_for_update()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="job not found")


def _require_investigator_job(session, job_id, user_id):
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    user = session.get(User, user_id)
    if user and user.global_role == UserRole.superuser:
        return job
    if job.owner_user_id == user_id:
        return job
    shared_copy = session.scalar(select(InvestigationShare).where(
        InvestigationShare.shared_job_id == job_id,
        InvestigationShare.owner_user_id == user_id,
    ))
    if shared_copy:
        return job
    if job.organization_id:
        membership = session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == job.organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.role == MembershipRole.investigator,
        ))
        if membership:
            return job
    raise HTTPException(status_code=403, detail="Investigator access to this investigation is required")


def correlation_to_response(
    row: Correlation,
) -> CorrelationResponse:
    return CorrelationResponse(
        id=row.id,
        job_id=row.job_id,
        finding_a_id=row.finding_a_id,
        finding_b_id=row.finding_b_id,
        correlation_type=row.correlation_type,
        basis=row.basis,
        assessment=row.assessment,
        assessment_note=row.assessment_note,
        assessment_updated_at=row.assessment_updated_at,
        created_at=row.created_at,
        evidence=[
            {
                "indicator_a_id": item.indicator_a_id,
                "indicator_b_id": item.indicator_b_id,
                "indicator_type": item.indicator_a.indicator_type,
                "normalized_value": item.indicator_a.normalized_value,
            }
            for item in row.evidence
        ],
    )


def finding_to_response(
    row: Finding,
) -> FindingResponse:
    return FindingResponse(
        id=row.id,
        module=row.module,
        source=row.source,
        source_url=row.source_url,
        input_value=row.input_value,
        input_type=row.input_type,
        finding_type=row.finding_type,
        value=row.value,
        evidence_strength=row.evidence_strength,
        match_reason=row.match_reason,

        identity_assessment=row.identity_assessment,
        relevance_assessment=row.relevance_assessment,
        assessment_note=row.assessment_note,
        assessment_updated_at=row.assessment_updated_at,

        raw_evidence=row.raw_evidence,
        created_at=row.created_at,

        indicators=[
            {
                "id": indicator.id,
                "indicator_type": indicator.indicator_type,
                "value": indicator.value,
                "normalized_value": indicator.normalized_value,
                "provenance_field": indicator.provenance_field,
            }
            for indicator in row.indicators
        ],
    )


def entity_to_response(row: Entity) -> EntityResponse:
    return EntityResponse(
        id=row.id,
        job_id=row.job_id,
        label=row.label,
        entity_type=row.entity_type,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
        findings=[
            {"id": item.id, "finding_id": item.finding_id, "role": item.role}
            for item in row.findings
        ],
    )


def relationship_to_response(row: Relationship) -> RelationshipResponse:
    return RelationshipResponse(
        id=row.id,
        job_id=row.job_id,
        entity_a_id=row.entity_a_id,
        entity_b_id=row.entity_b_id,
        relationship_type=row.relationship_type,
        basis=row.basis,
        assessment=row.assessment,
        assessment_note=row.assessment_note,
        assessment_updated_at=row.assessment_updated_at,
        created_at=row.created_at,
        evidence=[
            {
                "correlation_id": item.correlation_id,
                "finding_a_id": item.finding_a_id,
                "finding_b_id": item.finding_b_id,
            }
            for item in row.evidence
        ],
    )


@router.post(
    "/ingest/name",
    response_model=JobCreatedResponse,
    status_code=202,
)
def ingest_name(
    payload: IngestNameRequest,
    request: Request,
):
    requested_at = datetime.now(timezone.utc).isoformat()
    value = " ".join(
        payload.name.split()
    ).strip()

    if not value:
        raise HTTPException(
            status_code=422,
            detail="name cannot be empty",
        )

    with db_session() as session:
        repo = Repository(session)

        organization_id = payload.organization_id
        if organization_id:
            membership = session.scalar(select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == request.state.current_user_id,
                OrganizationMembership.is_active.is_(True),
            ))
            if not membership or membership.role != MembershipRole.investigator:
                raise HTTPException(status_code=403, detail="Active investigator membership required to create an organizational investigation")
        job = repo.create_job(
            value,
            "person_name",
        )
        job.owner_user_id = request.state.current_user_id
        job.organization_id = organization_id

        job_id = job.id

    process_person_name_job.delay(job_id, requested_at, None)

    return JobCreatedResponse(
        job_id=job_id,
        status="queued",
    )


@router.post(
    "/investigations",
    response_model=JobCreatedResponse,
    status_code=201,
)
def create_investigation(
    payload: InvestigationCreateRequest,
    request: Request,
):
    """Create a named investigation workspace without launching any search."""
    title = " ".join(payload.title.split()).strip()
    notes = (payload.notes or "").strip() or None
    if not title:
        raise HTTPException(status_code=422, detail="Investigation title cannot be empty")

    with db_session() as session:
        organization_id = payload.organization_id
        if organization_id:
            membership = session.scalar(select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == request.state.current_user_id,
                OrganizationMembership.is_active.is_(True),
            ))
            if not membership or membership.role != MembershipRole.investigator:
                raise HTTPException(status_code=403, detail="Active investigator membership required to create an organizational investigation")

        job = Repository(session).create_job(title, "investigation")
        job.investigation_title = title
        job.notes = notes
        job.status = JobStatus.draft
        job.owner_user_id = request.state.current_user_id
        job.organization_id = organization_id
        job_id = job.id

    # Deliberately do not enqueue process_person_name_job here.
    return JobCreatedResponse(job_id=job_id, status="draft")


@router.post(
    "/jobs/{job_id}/search/name",
    status_code=202,
)
def manual_name_search(job_id: str, payload: ManualNameSearchRequest, request: Request):
    query = " ".join(payload.query.split()).strip()
    requested_at = datetime.now(timezone.utc).isoformat()
    user_id = request.state.current_user_id
    with db_session() as session:
        _require_investigator_job(session, job_id, user_id)
        active_checkpoint = session.scalar(
            select(InvestigationCheckpoint)
            .where(
                InvestigationCheckpoint.job_id == job_id,
                InvestigationCheckpoint.user_id == user_id,
                InvestigationCheckpoint.status == "active",
            )
            .order_by(InvestigationCheckpoint.created_at.desc())
        )
        checkpoint_id = active_checkpoint.id if active_checkpoint else None
    task = process_manual_person_name_search.delay(job_id, query, requested_at, checkpoint_id)
    return {"job_id": job_id, "query": query, "task_id": task.id, "status": "queued"}


@router.get(
    "/jobs",
    response_model=list[JobResponse],
)
def list_jobs(request: Request):
    """List investigations visible to the authenticated user, newest first."""
    user_id = request.state.current_user_id

    with db_session() as session:
        actor = session.get(User, user_id)
        job_query = select(Job).order_by(Job.created_at.desc())
        if actor and actor.global_role == UserRole.superuser:
            jobs = session.scalars(job_query).all()
        else:
            entity_organization_ids = select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
                OrganizationMembership.role == MembershipRole.entity,
            )
            jobs = session.scalars(
                job_query.where(
                    or_(
                        Job.owner_user_id == user_id,
                        Job.organization_id.in_(entity_organization_ids),
                    )
                )
            ).all()

        result = []
        for job in jobs:
            result.append(
                JobResponse(
                    id=job.id,
                    is_owner=(job.owner_user_id == user_id),
                    is_shared=(session.scalar(select(InvestigationShare.id).where(InvestigationShare.shared_job_id == job.id)) is not None),
                    can_edit=bool(
                        actor
                        and (
                            actor.global_role == UserRole.superuser
                            or (
                                actor.global_role not in {UserRole.user, UserRole.entity}
                                and job.owner_user_id == user_id
                                and (
                                    (share := session.scalar(select(InvestigationShare).where(InvestigationShare.shared_job_id == job.id))) is None
                                    or share.permission == "edit"
                                )
                            )
                        )
                    ),
                    input_value=job.input_value,
                    investigation_title=job.investigation_title,
                    notes=job.notes,
                    input_type=job.input_type,
                    status=job.status.value,
                    error=job.error,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    finding_count=session.scalar(
                        select(func.count(Finding.id)).where(Finding.job_id == job.id)
                    ) or 0,
                    correlation_count=session.scalar(
                        select(func.count(Correlation.id)).where(Correlation.job_id == job.id)
                    ) or 0,
                    module_runs=[
                        {
                            "id": run.id,
                            "module": run.module,
                            "source": run.source,
                            "query": run.query,
                            "status": run.status.value,
                            "http_status": run.http_status,
                            "error": run.error,
                            "rate_limit_remaining": run.rate_limit_remaining,
                            "started_at": run.started_at,
                            "finished_at": run.finished_at,
                        }
                        for run in job.runs
                    ],
                )
            )
        return result


@router.delete("/jobs/{job_id}", status_code=204)
def delete_investigation(job_id: str, request: Request):
    """Permanently delete an investigation and its dependent evidence."""
    user_id = request.state.current_user_id
    with db_session() as session:
        job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job:
            raise HTTPException(status_code=404, detail="Investigation not found")
        actor = session.get(User, user_id)
        share = session.scalar(select(InvestigationShare).where(InvestigationShare.shared_job_id == job_id))
        can_delete = bool(actor and (
            actor.global_role == UserRole.superuser
            or job.owner_user_id == user_id
            or (share and share.owner_user_id == user_id)
        ))
        if not can_delete:
            raise HTTPException(status_code=403, detail="Only the investigation owner can delete it or revoke its shared copy")
        # Removing an original also removes every collaborator copy first; otherwise
        # the copies would remain as orphaned investigations after share metadata cascades.
        if share is None:
            related_shares = session.scalars(select(InvestigationShare).where(
                InvestigationShare.original_job_id == job_id
            )).all()
            for related_share in related_shares:
                copy_tables, copy_rows = _collect_investigation_rows(session, related_share.shared_job_id)
                for copy_table in reversed(copy_tables):
                    for copy_row in copy_rows.get(copy_table.name, []):
                        copy_keys = [column == copy_row[column.name] for column in copy_table.primary_key.columns]
                        if copy_keys:
                            session.execute(delete(copy_table).where(and_(*copy_keys)))
        tables, rows_by_table = _collect_investigation_rows(session, job_id)
        # Remove dependent rows in reverse FK order, then the investigation.
        for table in reversed(tables):
            for row in rows_by_table.get(table.name, []):
                keys = [column == row[column.name] for column in table.primary_key.columns]
                if keys:
                    session.execute(delete(table).where(and_(*keys)))
        session.flush()
    from fastapi import Response
    return Response(status_code=204)


@router.post("/jobs/{job_id}/shares", status_code=201)
def share_investigation(job_id: str, payload: dict, request: Request):
    """Create a separate working copy for one registered investigator."""
    user_id = request.state.current_user_id
    email = str(payload.get("email", "")).strip().lower()
    permission = payload.get("permission", "read")
    if permission not in {"read", "comment", "edit"}:
        raise HTTPException(status_code=422, detail="Permission must be read, comment or edit")
    if not email:
        raise HTTPException(status_code=422, detail="Collaborator email is required")
    with db_session() as session:
        original = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not original:
            raise HTTPException(status_code=404, detail="Investigation not found")
        if original.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Only the original investigator can share this investigation")
        if session.scalar(select(InvestigationShare.id).where(InvestigationShare.shared_job_id == job_id)):
            raise HTTPException(status_code=403, detail="A shared copy cannot be shared again")
        collaborator = session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if not collaborator:
            raise HTTPException(status_code=404, detail="No active account exists for that email")
        if collaborator.global_role != UserRole.investigator:
            raise HTTPException(status_code=422, detail="Only investigator accounts can collaborate")
        if collaborator.id == user_id:
            raise HTTPException(status_code=422, detail="You cannot share an investigation with yourself")
        existing = session.scalar(select(InvestigationShare).where(
            InvestigationShare.original_job_id == job_id,
            InvestigationShare.collaborator_user_id == collaborator.id,
        ))
        if existing:
            raise HTTPException(status_code=409, detail="This investigator already has a shared copy")

        base_snapshot = _make_investigation_snapshot(session, job_id)
        tables, rows_by_table = _collect_investigation_rows(session, job_id)
        id_map = {}
        for table in tables:
            pk_columns = list(table.primary_key.columns)
            if len(pk_columns) != 1:
                raise HTTPException(status_code=500, detail=f"Cannot clone table with composite primary key: {table.name}")
            pk = pk_columns[0].name
            id_map[table.name] = {
                str(row[pk]): str(uuid.uuid4()) for row in rows_by_table.get(table.name, [])
            }
        shared_job_id = id_map["jobs"][job_id]
        for table in tables:
            for source_row in rows_by_table.get(table.name, []):
                row = dict(source_row)
                pk = list(table.primary_key.columns)[0].name
                old_pk = str(row[pk])
                row[pk] = id_map[table.name][old_pk]
                for fk in table.foreign_keys:
                    parent_map = id_map.get(fk.column.table.name, {})
                    if str(row.get(fk.parent.name)) in parent_map:
                        row[fk.parent.name] = parent_map[str(row[fk.parent.name])]
                if table.name == "jobs":
                    row["owner_user_id"] = collaborator.id
                    row["organization_id"] = None
                session.execute(insert(table).values(**row))
        share = InvestigationShare(
            original_job_id=job_id,
            shared_job_id=shared_job_id,
            owner_user_id=user_id,
            collaborator_user_id=collaborator.id,
            permission=permission,
            base_snapshot=base_snapshot,
            id_map=id_map,
        )
        session.add(share)
        session.flush()
        return {"share_id": share.id, "original_job_id": job_id, "shared_job_id": shared_job_id,
                "collaborator_email": collaborator.email, "permission": permission}


@router.get("/jobs/{job_id}/shares")
def list_investigation_shares(job_id: str, request: Request):
    user_id = request.state.current_user_id
    with db_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Investigation not found")
        if job.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Only the original investigator can list shares")
        shares = session.scalars(select(InvestigationShare).where(
            InvestigationShare.original_job_id == job_id
        ).order_by(InvestigationShare.created_at.desc())).all()
        result = []
        for share in shares:
            current_copy = _make_investigation_snapshot(session, share.shared_job_id)
            result.append({
                "share_id": share.id, "shared_job_id": share.shared_job_id,
                "email": session.get(User, share.collaborator_user_id).email,
                "permission": share.permission, "created_at": share.created_at,
                "reviewed": share.reviewed_snapshot is not None and current_copy == share.reviewed_snapshot,
                "reviewed_at": share.reviewed_at,
            })
        return result


@router.get("/shared-investigations")
def list_shared_investigations(request: Request):
    user_id = request.state.current_user_id
    with db_session() as session:
        shares = session.scalars(select(InvestigationShare).where(
            InvestigationShare.collaborator_user_id == user_id
        ).order_by(InvestigationShare.created_at.desc())).all()
        return [{"share_id": s.id, "job_id": s.shared_job_id, "original_job_id": s.original_job_id,
                 "permission": s.permission, "created_at": s.created_at,
                 "title": session.get(Job, s.shared_job_id).investigation_title if session.get(Job, s.shared_job_id) else None}
                for s in shares]


@router.get("/jobs/{job_id}/shares/{share_id}/review")
def review_shared_investigation(job_id: str, share_id: str, request: Request):
    """Return the row-level proposal diff without changing either investigation."""
    user_id = request.state.current_user_id
    with db_session() as session:
        share = session.get(InvestigationShare, share_id)
        if not share or share.original_job_id != job_id:
            raise HTTPException(status_code=404, detail="Shared investigation not found")
        if share.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Only the original investigator can review this proposal")
        current_copy = _make_investigation_snapshot(session, share.shared_job_id)
        normalized_copy = _normalize_shared_snapshot(current_copy, share, share.base_snapshot)
        changes = _investigation_snapshot_diff(share.base_snapshot, normalized_copy)
        return {
            "share_id": share.id, "original_job_id": share.original_job_id,
            "shared_job_id": share.shared_job_id,
            "collaborator_email": session.get(User, share.collaborator_user_id).email,
            "permission": share.permission, "changes": changes,
            "change_count": sum(item["added"] + item["deleted"] + item["modified"] for item in changes),
            "reviewed": share.reviewed_snapshot is not None and current_copy == share.reviewed_snapshot,
            "reviewed_at": share.reviewed_at,
        }


@router.post("/jobs/{job_id}/shares/{share_id}/review")
def mark_shared_investigation_reviewed(job_id: str, share_id: str, request: Request):
    """Record the exact collaborator snapshot that the owner has reviewed."""
    user_id = request.state.current_user_id
    with db_session() as session:
        original = session.get(Job, job_id)
        share = session.get(InvestigationShare, share_id)
        if not original or not share or share.original_job_id != job_id:
            raise HTTPException(status_code=404, detail="Shared investigation not found")
        if original.owner_user_id != user_id or share.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Only the original investigator can review this proposal")
        share.reviewed_snapshot = _make_investigation_snapshot(session, share.shared_job_id)
        share.reviewed_at = datetime.now(timezone.utc)
        session.flush()
        return {"share_id": share.id, "reviewed": True, "reviewed_at": share.reviewed_at}


@router.post("/shares/{share_id}/comments", status_code=201)
def add_investigation_comment(share_id: str, payload: dict, request: Request):
    user_id = request.state.current_user_id
    body = str(payload.get("body", "")).strip()
    if not body or len(body) > 10000:
        raise HTTPException(status_code=422, detail="Comment must contain 1–10000 characters")
    with db_session() as session:
        share = session.get(InvestigationShare, share_id)
        if not share or user_id not in {share.owner_user_id, share.collaborator_user_id}:
            raise HTTPException(status_code=404, detail="Shared investigation not found")
        if user_id == share.collaborator_user_id and share.permission == "read":
            raise HTTPException(status_code=403, detail="This share is read-only; comments are not permitted")
        comment = InvestigationComment(share_id=share_id, author_user_id=user_id, body=body)
        session.add(comment)
        session.flush()
        return {"id": comment.id, "share_id": share_id, "author_email": session.get(User, user_id).email,
                "body": comment.body, "created_at": comment.created_at}


@router.get("/shares/{share_id}/comments")
def list_investigation_comments(share_id: str, request: Request):
    user_id = request.state.current_user_id
    with db_session() as session:
        share = session.get(InvestigationShare, share_id)
        if not share or user_id not in {share.owner_user_id, share.collaborator_user_id}:
            raise HTTPException(status_code=404, detail="Shared investigation not found")
        comments = session.scalars(select(InvestigationComment).where(
            InvestigationComment.share_id == share_id
        ).order_by(InvestigationComment.created_at.asc())).all()
        return [{"id": c.id, "author_email": session.get(User, c.author_user_id).email,
                 "body": c.body, "created_at": c.created_at} for c in comments]


@router.post("/jobs/{job_id}/shares/{share_id}/merge")
def merge_shared_investigation(job_id: str, share_id: str, request: Request):
    """Pull a shared copy back only when the original has not changed since sharing."""
    user_id = request.state.current_user_id
    with db_session() as session:
        original = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        share = session.get(InvestigationShare, share_id)
        if not original or not share or share.original_job_id != job_id:
            raise HTTPException(status_code=404, detail="Share or original investigation not found")
        if original.owner_user_id != user_id or share.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Only the original investigator can merge a shared copy")
        current_copy_snapshot = _make_investigation_snapshot(session, share.shared_job_id)
        if share.reviewed_snapshot is None or current_copy_snapshot != share.reviewed_snapshot:
            raise HTTPException(status_code=409, detail="Review the current collaborator changes before pulling or merging them.")
        current_baseline = _make_investigation_snapshot(session, job_id)
        if current_baseline != share.base_snapshot:
            raise HTTPException(status_code=409, detail="The original changed after sharing. Reconcile the changes before merging.")
        tables, original_rows = _collect_investigation_rows(session, job_id)
        shared_tables, shared_rows = _collect_investigation_rows(session, share.shared_job_id)
        reverse_map = {table: {copy_id: original_id for original_id, copy_id in mapping.items()}
                       for table, mapping in share.id_map.items()}
        target_ids = {}
        for table in shared_tables:
            pk = list(table.primary_key.columns)[0].name
            target_ids[table.name] = {}
            for row in shared_rows.get(table.name, []):
                copied_id = str(row[pk])
                target_ids[table.name][copied_id] = (
                    job_id if table.name == "jobs" else
                    reverse_map.get(table.name, {}).get(copied_id, str(uuid.uuid4()))
                )
        for table in reversed(tables):
            if table.name == "jobs":
                continue
            for row in original_rows.get(table.name, []):
                keys = [column == row[column.name] for column in table.primary_key.columns]
                if keys:
                    session.execute(delete(table).where(and_(*keys)))
        for table in shared_tables:
            if table.name == "jobs":
                continue
            for source_row in shared_rows.get(table.name, []):
                row = dict(source_row)
                pk = list(table.primary_key.columns)[0].name
                row[pk] = target_ids[table.name][str(source_row[pk])]
                for fk in table.foreign_keys:
                    parent_map = target_ids.get(fk.column.table.name, {})
                    if str(row.get(fk.parent.name)) in parent_map:
                        row[fk.parent.name] = parent_map[str(row[fk.parent.name])]
                session.execute(insert(table).values(**row))
        shared_job = session.get(Job, share.shared_job_id)
        original.investigation_title = shared_job.investigation_title
        original.notes = shared_job.notes
        original.input_value = shared_job.input_value
        session.flush()
        # Advance the collaboration baseline so the same share can be merged again
        # after further collaborator edits, while still detecting concurrent changes.
        share.base_snapshot = _make_investigation_snapshot(session, job_id)
        share.reviewed_snapshot = None
        share.reviewed_at = None
        share.id_map = {
            table_name: {original_id: copy_id for copy_id, original_id in mapping.items()}
            for table_name, mapping in target_ids.items()
        }
        return {"job_id": job_id, "share_id": share_id, "status": "merged", "baseline_advanced": True}


@router.post("/jobs/{job_id}/checkpoint")
def create_investigation_checkpoint(job_id: str, request: Request):
    """Capture the baseline once when an investigator opens an editing session."""
    user_id = request.state.current_user_id
    with db_session() as session:
        _require_investigator_job(session, job_id, user_id)
        active = session.scalar(
            select(InvestigationCheckpoint)
            .where(
                InvestigationCheckpoint.job_id == job_id,
                InvestigationCheckpoint.status.in_(("active", "restoring")),
            )
            .order_by(InvestigationCheckpoint.created_at.desc())
        )
        if active and active.user_id != user_id:
            raise HTTPException(
                status_code=409,
                detail="Esta investigación ya tiene una sesión de edición activa en otro usuario.",
            )
        if active and active.status == "active":
            return {"job_id": job_id, "checkpoint_id": active.id, "status": active.status, "reused": True}
        if active and active.status == "restoring":
            # Recover an interrupted discard before allowing another editing session.
            _restore_investigation_snapshot(session, job_id, active.snapshot)
            active.status = "discarded"
            active.closed_at = datetime.now(timezone.utc)
            session.flush()

        snapshot = _make_investigation_snapshot(session, job_id)
        checkpoint = InvestigationCheckpoint(
            job_id=job_id,
            user_id=user_id,
            status="active",
            snapshot=snapshot,
        )
        session.add(checkpoint)
        session.flush()
        return {"job_id": job_id, "checkpoint_id": checkpoint.id, "status": checkpoint.status, "reused": False}


@router.post("/jobs/{job_id}/checkpoint/commit")
def commit_investigation_checkpoint(job_id: str, request: Request):
    """Keep all session changes and close the restore point."""
    user_id = request.state.current_user_id
    with db_session() as session:
        _require_investigator_job(session, job_id, user_id)
        checkpoint = session.scalar(
            select(InvestigationCheckpoint)
            .where(
                InvestigationCheckpoint.job_id == job_id,
                InvestigationCheckpoint.status == "active",
            )
            .order_by(InvestigationCheckpoint.created_at.desc())
        )
        if not checkpoint:
            return {"job_id": job_id, "status": "no_active_checkpoint"}
        if checkpoint.user_id != user_id:
            raise HTTPException(status_code=409, detail="La sesión activa pertenece a otro usuario.")
        checkpoint.status = "committed"
        checkpoint.closed_at = datetime.now(timezone.utc)
        return {"job_id": job_id, "checkpoint_id": checkpoint.id, "status": checkpoint.status}


@router.post("/jobs/{job_id}/checkpoint/restore")
def restore_investigation_checkpoint(job_id: str, request: Request):
    """Revert all investigation-scoped database changes to the session baseline."""
    user_id = request.state.current_user_id
    with db_session() as session:
        _require_investigator_job(session, job_id, user_id)
        checkpoint = session.scalar(
            select(InvestigationCheckpoint)
            .where(
                InvestigationCheckpoint.job_id == job_id,
                InvestigationCheckpoint.status.in_(("active", "restoring")),
            )
            .order_by(InvestigationCheckpoint.created_at.desc())
        )
        if not checkpoint:
            raise HTTPException(status_code=409, detail="No hay un punto de restauración activo para esta sesión.")
        if checkpoint.user_id != user_id:
            raise HTTPException(status_code=409, detail="La sesión activa pertenece a otro usuario.")

        checkpoint_id = checkpoint.id
        snapshot = checkpoint.snapshot
        checkpoint.status = "restoring"
        try:
            # Keep the job lock and this transaction until the entire restore is
            # complete. Workers use the same lock, so none can write between the
            # baseline replacement and the terminal checkpoint state.
            _restore_investigation_snapshot(session, job_id, snapshot)
            checkpoint = session.get(InvestigationCheckpoint, checkpoint_id)
            checkpoint.status = "discarded"
            checkpoint.closed_at = datetime.now(timezone.utc)
            session.commit()
        except Exception as exc:
            session.rollback()
            failed_checkpoint = session.get(InvestigationCheckpoint, checkpoint_id)
            if failed_checkpoint:
                failed_checkpoint.status = "active"
                session.commit()
            raise HTTPException(status_code=500, detail=f"No se pudo restaurar la investigación: {exc}") from exc
        return {"job_id": job_id, "checkpoint_id": checkpoint_id, "status": "discarded", "restored": True}


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
)
def get_job(
    job_id: str,
    request: Request,
):
    with db_session() as session:
        repo = Repository(session)

        job = repo.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail="job not found",
            )

        finding_count = (
            session.scalar(
                select(
                    func.count(Finding.id)
                ).where(
                    Finding.job_id == job_id
                )
            )
            or 0
        )

        user_id = request.state.current_user_id
        actor = session.get(User, user_id)
        share = session.scalar(select(InvestigationShare).where(InvestigationShare.shared_job_id == job.id))
        can_edit = bool(
            actor
            and (
                actor.global_role == UserRole.superuser
                or (
                    actor.global_role not in {UserRole.user, UserRole.entity}
                    and job.owner_user_id == user_id
                    and (share is None or share.permission == "edit")
                )
            )
        )
        return JobResponse(
            id=job.id,
            is_owner=(job.owner_user_id == user_id),
            is_shared=(share is not None),
            can_edit=can_edit,
            input_value=job.input_value,
            investigation_title=job.investigation_title,
            notes=job.notes,
            input_type=job.input_type,
            status=job.status.value,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            finding_count=finding_count,
            correlation_count=session.scalar(
                select(func.count(Correlation.id)).where(
                    Correlation.job_id == job_id
                )
            ) or 0,

            module_runs=[
                {
                    "id": run.id,
                    "module": run.module,
                    "source": run.source,
                    "query": run.query,
                    "status": run.status.value,
                    "http_status": run.http_status,
                    "error": run.error,
                    "rate_limit_remaining": run.rate_limit_remaining,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                }
                for run in job.runs
            ],
        )


@router.get(
    "/jobs/{job_id}/findings",
    response_model=list[FindingResponse],
)
def get_findings(
    job_id: str,
):
    with db_session() as session:
        repo = Repository(session)

        if not repo.get_job(job_id):
            raise HTTPException(
                status_code=404,
                detail="job not found",
            )

        rows = repo.get_findings(job_id)

        return [
            finding_to_response(row)
            for row in rows
        ]


@router.get(
    "/jobs/{job_id}/correlations",
    response_model=list[CorrelationResponse],
)
def get_correlations(
    job_id: str,
):
    with db_session() as session:
        repo = Repository(session)

        if not repo.get_job(job_id):
            raise HTTPException(
                status_code=404,
                detail="job not found",
            )

        rows = repo.get_correlations(job_id)
        return [correlation_to_response(row) for row in rows]


@router.get(
    "/jobs/{job_id}/graph",
    response_model=GraphResponse,
)
def get_graph(job_id: str):
    with db_session() as session:
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        return repo.get_graph(job_id)


@router.post(
    "/jobs/{job_id}/entities",
    response_model=EntityResponse,
    status_code=201,
)
def create_entity(job_id: str, payload: EntityCreateRequest):
    with db_session() as session:
        _lock_job_for_mutation(session, job_id)
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        try:
            entity = repo.create_entity(
                job_id, payload.label, entity_type=payload.entity_type,
                description=payload.description,
                finding_ids=payload.finding_ids,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        entity = repo.get_entity(entity.id)
        return entity_to_response(entity)


@router.patch(
    "/entities/{entity_id}",
    response_model=EntityResponse,
)
def update_entity(entity_id: str, payload: EntityUpdateRequest):
    with db_session() as session:
        repo = Repository(session)
        job_id = session.scalar(select(Entity.job_id).where(Entity.id == entity_id))
        if not job_id:
            raise HTTPException(status_code=404, detail="entity not found")
        _lock_job_for_mutation(session, job_id)
        entity = repo.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="entity not found")
        repo.update_entity(
            entity,
            label=payload.label,
            description=payload.description,
        )
        session.commit()
        return entity_to_response(repo.get_entity(entity_id))


@router.get(
    "/jobs/{job_id}/entities",
    response_model=list[EntityResponse],
)
def get_entities(job_id: str):
    with db_session() as session:
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        return [entity_to_response(row) for row in repo.get_entities(job_id)]


@router.get(
    "/entities/{entity_id}/profile",
    response_model=ProfileResponse,
)
def get_entity_profile(entity_id: str):
    with db_session() as session:
        repo = Repository(session)
        entity = repo.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="entity not found")

        relationships = [
            row for row in repo.get_relationships(entity.job_id)
            if row.entity_a_id == entity.id or row.entity_b_id == entity.id
        ]
        findings = [item.finding for item in entity.findings]
        indicator_map = {}
        for finding in findings:
            for indicator in finding.indicators:
                indicator_map[(indicator.indicator_type, indicator.normalized_value)] = indicator

        return ProfileResponse(
            id=entity.id,
            job_id=entity.job_id,
            label=entity.label,
            entity_type=entity.entity_type,
            description=entity.description,
            findings=[finding_to_response(row) for row in findings],
            indicators=[
                {
                    "id": item.id,
                    "indicator_type": item.indicator_type,
                    "value": item.value,
                    "normalized_value": item.normalized_value,
                    "provenance_field": item.provenance_field,
                }
                for item in indicator_map.values()
            ],
            relationships=[relationship_to_response(row) for row in relationships],
        )


@router.post(
    "/entities/{entity_id}/findings",
    response_model=EntityResponse,
)
def attach_finding(entity_id: str, payload: EntityFindingAttachRequest):
    with db_session() as session:
        repo = Repository(session)
        job_id = session.scalar(select(Entity.job_id).where(Entity.id == entity_id))
        if not job_id:
            raise HTTPException(status_code=404, detail="entity not found")
        _lock_job_for_mutation(session, job_id)
        entity = repo.get_entity(entity_id)
        finding = repo.get_finding(payload.finding_id)
        if not entity:
            raise HTTPException(status_code=404, detail="entity not found")
        if not finding:
            raise HTTPException(status_code=404, detail="finding not found")
        try:
            repo.attach_finding_to_entity(entity, finding, role=payload.role)
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        entity = repo.get_entity(entity_id)
        return entity_to_response(entity)


@router.post(
    "/jobs/{job_id}/relationships",
    response_model=RelationshipResponse,
    status_code=201,
)
def create_relationship(job_id: str, payload: RelationshipCreateRequest):
    with db_session() as session:
        _lock_job_for_mutation(session, job_id)
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        entity_a = repo.get_entity(payload.entity_a_id)
        entity_b = repo.get_entity(payload.entity_b_id)
        if not entity_a or not entity_b:
            raise HTTPException(status_code=404, detail="entity not found")
        if entity_a.job_id != job_id or entity_b.job_id != job_id:
            raise HTTPException(status_code=422, detail="entities must belong to the job")
        if payload.correlation_id:
            correlation = session.get(Correlation, payload.correlation_id)
            if not correlation or correlation.job_id != job_id:
                raise HTTPException(status_code=422, detail="correlation does not belong to the job")
        try:
            relationship = repo.create_relationship(
                job_id, entity_a, entity_b,
                relationship_type=payload.relationship_type,
                basis=payload.basis,
                assessment=payload.assessment,
                correlation_id=payload.correlation_id,
                finding_a_id=payload.finding_a_id,
                finding_b_id=payload.finding_b_id,
            )
            relationship_id = relationship.id
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        created = next(
            row for row in repo.get_relationships(job_id)
            if row.id == relationship_id
        )
        return relationship_to_response(created)


@router.patch(
    "/relationships/{relationship_id}",
    response_model=RelationshipResponse,
)
def update_relationship(relationship_id: str, payload: RelationshipUpdateRequest):
    with db_session() as session:
        repo = Repository(session)
        job_id = session.scalar(select(Relationship.job_id).where(Relationship.id == relationship_id))
        if not job_id:
            raise HTTPException(status_code=404, detail="relationship not found")
        _lock_job_for_mutation(session, job_id)
        relationship = session.get(Relationship, relationship_id)
        if not relationship:
            raise HTTPException(status_code=404, detail="relationship not found")
        try:
            repo.update_relationship(
                relationship,
                relationship_type=payload.relationship_type,
                basis=payload.basis,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        created = next(
            row for row in repo.get_relationships(relationship.job_id)
            if row.id == relationship_id
        )
        return relationship_to_response(created)


@router.get(
    "/jobs/{job_id}/relationships",
    response_model=list[RelationshipResponse],
)
def get_relationships(job_id: str):
    with db_session() as session:
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        return [relationship_to_response(row) for row in repo.get_relationships(job_id)]


@router.patch(
    "/relationships/{relationship_id}/assessment",
    response_model=RelationshipResponse,
)
def assess_relationship(relationship_id: str, payload: RelationshipAssessmentRequest):
    with db_session() as session:
        repo = Repository(session)
        job_id = session.scalar(select(Relationship.job_id).where(Relationship.id == relationship_id))
        if not job_id:
            raise HTTPException(status_code=404, detail="relationship not found")
        _lock_job_for_mutation(session, job_id)
        relationship = session.get(Relationship, relationship_id)
        if not relationship:
            raise HTTPException(status_code=404, detail="relationship not found")
        repo.assess_relationship(
            relationship,
            assessment=payload.assessment,
            assessment_note=payload.assessment_note,
            update_note="assessment_note" in payload.model_fields_set,
        )
        session.commit()
        created = next(
            row for row in repo.get_relationships(relationship.job_id)
            if row.id == relationship_id
        )
        return relationship_to_response(created)


@router.patch(
    "/correlations/{correlation_id}/assessment",
    response_model=CorrelationResponse,
)
def assess_correlation(
    correlation_id: str,
    payload: CorrelationAssessmentRequest,
):
    with db_session() as session:
        repo = Repository(session)
        job_id = session.scalar(select(Correlation.job_id).where(Correlation.id == correlation_id))
        if not job_id:
            raise HTTPException(
                status_code=404,
                detail="correlation not found",
            )

        _lock_job_for_mutation(session, job_id)
        correlation = session.get(Correlation, correlation_id)
        if not correlation:
            raise HTTPException(status_code=404, detail="correlation not found")
        updated = repo.assess_correlation(
            correlation,
            assessment=payload.assessment,
            assessment_note=payload.assessment_note,
            update_note="assessment_note" in payload.model_fields_set,
        )

        # Reload relationships for response serialization.
        rows = repo.get_correlations(correlation.job_id)
        updated = next(row for row in rows if row.id == correlation_id)
        return correlation_to_response(updated)


@router.patch(
    "/findings/{finding_id}/assessment",
    response_model=FindingResponse,
)
def assess_finding(
    finding_id: str,
    payload: FindingAssessmentRequest,
):
    with db_session() as session:
        repo = Repository(session)
        job_id = session.scalar(select(Finding.job_id).where(Finding.id == finding_id))
        if not job_id:
            raise HTTPException(
                status_code=404,
                detail="finding not found",
            )

        _lock_job_for_mutation(session, job_id)
        finding = repo.get_finding(finding_id)
        if not finding:
            raise HTTPException(status_code=404, detail="finding not found")
        updated = repo.assess_finding(
            finding,
            identity_assessment=payload.identity_assessment,
            relevance_assessment=payload.relevance_assessment,
            assessment_note=payload.assessment_note,
            update_note=(
                "assessment_note"
                in payload.model_fields_set
            ),
        )

        return finding_to_response(updated)