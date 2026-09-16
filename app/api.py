from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.db import db_session
from app.models import Correlation, Finding
from app.repository import Repository
from app.schemas import (
    CorrelationAssessmentRequest,
    CorrelationResponse,
    FindingAssessmentRequest,
    FindingResponse,
    IngestNameRequest,
    JobCreatedResponse,
    JobResponse,
)
from app.tasks import process_person_name_job


router = APIRouter(prefix="/api/v1")


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


@router.post(
    "/ingest/name",
    response_model=JobCreatedResponse,
    status_code=202,
)
def ingest_name(
    payload: IngestNameRequest,
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

        job = repo.create_job(
            value,
            "person_name",
        )

        job_id = job.id

    process_person_name_job.delay(job_id)

    return JobCreatedResponse(
        job_id=job_id,
        status="queued",
    )


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