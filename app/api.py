from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.db import db_session
from app.models import Finding
from app.repository import Repository
from app.schemas import FindingResponse, IngestNameRequest, JobCreatedResponse, JobResponse
from app.tasks import process_person_name_job

router = APIRouter(prefix="/api/v1")


@router.post("/ingest/name", response_model=JobCreatedResponse, status_code=202)
def ingest_name(payload: IngestNameRequest):
    value = " ".join(payload.name.split()).strip()
    if not value:
        raise HTTPException(status_code=422, detail="name cannot be empty")

    with db_session() as session:
        repo = Repository(session)
        job = repo.create_job(value, "person_name")
        job_id = job.id

    process_person_name_job.delay(job_id)
    return JobCreatedResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    with db_session() as session:
        repo = Repository(session)
        job = repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        finding_count = session.scalar(
            select(func.count(Finding.id)).where(Finding.job_id == job_id)
        ) or 0

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
            module_runs=[
                {
                    "id": r.id,
                    "module": r.module,
                    "source": r.source,
                    "query": r.query,
                    "status": r.status.value,
                    "http_status": r.http_status,
                    "error": r.error,
                    "rate_limit_remaining": r.rate_limit_remaining,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                }
                for r in job.runs
            ],
        )


@router.get("/jobs/{job_id}/findings", response_model=list[FindingResponse])
def get_findings(job_id: str):
    with db_session() as session:
        repo = Repository(session)
        if not repo.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")

        rows = repo.get_findings(job_id)
        return [
            FindingResponse(
                id=row.id,
                module=row.module,
                source=row.source,
                source_url=row.source_url,
                input_value=row.input_value,
                input_type=row.input_type,
                finding_type=row.finding_type,
                value=row.value,
                confidence=row.confidence,
                relevance_reason=row.relevance_reason,
                raw_evidence=row.raw_evidence,
                created_at=row.created_at,
                indicators=[
                    {
                        "id": i.id,
                        "indicator_type": i.indicator_type,
                        "value": i.value,
                        "normalized_value": i.normalized_value,
                        "provenance_field": i.provenance_field,
                    }
                    for i in row.indicators
                ],
            )
            for row in rows
        ]
