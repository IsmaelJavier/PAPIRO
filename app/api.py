from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import authorize_api_request
from sqlalchemy import func, or_, select

from app.db import db_session
from app.models import Correlation, Entity, Finding, Job, MembershipRole, OrganizationMembership, Relationship
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
    JobCreatedResponse,
    JobResponse,
)
from app.tasks import process_person_name_job, process_manual_person_name_search


router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize_api_request)])


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

    process_person_name_job.delay(job_id)

    return JobCreatedResponse(
        job_id=job_id,
        status="queued",
    )


@router.post(
    "/jobs/{job_id}/search/name",
    status_code=202,
)
def manual_name_search(job_id: str, payload: ManualNameSearchRequest):
    query = " ".join(payload.query.split()).strip()
    with db_session() as session:
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
    task = process_manual_person_name_search.delay(job_id, query)
    return {"job_id": job_id, "query": query, "task_id": task.id, "status": "queued"}


@router.get(
    "/jobs",
    response_model=list[JobResponse],
)
def list_jobs(request: Request):
    """List investigations visible to the authenticated user, newest first."""
    user_id = request.state.current_user_id

    with db_session() as session:
        organization_ids = select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        )
        jobs = session.scalars(
            select(Job)
            .where(
                or_(
                    Job.owner_user_id == user_id,
                    Job.organization_id.in_(organization_ids),
                )
            )
            .order_by(Job.created_at.desc())
        ).all()

        result = []
        for job in jobs:
            result.append(
                JobResponse(
                    id=job.id,
                    input_value=job.input_value,
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


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
)
def get_job(
    job_id: str,
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

        return JobResponse(
            id=job.id,
            input_value=job.input_value,
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
        correlation = session.get(Correlation, correlation_id)

        if not correlation:
            raise HTTPException(
                status_code=404,
                detail="correlation not found",
            )

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

        finding = repo.get_finding(
            finding_id
        )

        if not finding:
            raise HTTPException(
                status_code=404,
                detail="finding not found",
            )

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