from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain import CanonicalFinding, ExtractedIndicator
from app.models import Finding, Indicator, Job, JobStatus, ModuleRun, RunStatus


def utcnow():
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_job(self, input_value: str, input_type: str) -> Job:
        job = Job(input_value=input_value, input_type=input_type, status=JobStatus.queued)
        self.session.add(job)
        self.session.flush()
        return job

    def get_job(self, job_id: str) -> Job | None:
        stmt = select(Job).where(Job.id == job_id).options(selectinload(Job.runs))
        return self.session.scalar(stmt)

    def mark_job_running(self, job: Job):
        job.status = JobStatus.running
        job.started_at = utcnow()
        job.error = None

    def mark_job_finished(self, job: Job, status: JobStatus, error: str | None = None):
        job.status = status
        job.completed_at = utcnow()
        job.error = error

    def create_run(self, job_id: str, module: str, source: str, query: str) -> ModuleRun:
        run = ModuleRun(job_id=job_id, module=module, source=source, query=query, status=RunStatus.success, started_at=utcnow())
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(self, run: ModuleRun, status: RunStatus, http_status: int | None = None,
                   error: str | None = None, rate_limit_remaining: int | None = None):
        run.status = status
        run.http_status = http_status
        run.error = error
        run.rate_limit_remaining = rate_limit_remaining
        run.finished_at = utcnow()

    def add_finding(self, job_id: str, finding: CanonicalFinding,
                    indicators: list[ExtractedIndicator]) -> Finding:
        existing = self.session.scalar(select(Finding).where(
            Finding.job_id == job_id,
            Finding.dedupe_key == finding.dedupe_key,
        ))
        if existing:
            return existing

        row = Finding(
            job_id=job_id,
            module=finding.module,
            source=finding.source,
            source_url=finding.source_url,
            input_value=finding.input_value,
            input_type=finding.input_type,
            finding_type=finding.finding_type,
            value=finding.value,
            confidence=finding.confidence,
            relevance_reason=finding.relevance_reason,
            dedupe_key=finding.dedupe_key,
            raw_evidence=finding.raw_evidence,
        )
        self.session.add(row)
        self.session.flush()

        seen = set()
        for indicator in indicators:
            key = (indicator.indicator_type, indicator.normalized_value)
            if key in seen:
                continue
            seen.add(key)
            self.session.add(Indicator(
                finding_id=row.id,
                indicator_type=indicator.indicator_type,
                value=indicator.value,
                normalized_value=indicator.normalized_value,
                provenance_field=indicator.provenance_field,
            ))

        self.session.flush()
        return row

    def get_findings(self, job_id: str) -> list[Finding]:
        stmt = select(Finding).where(Finding.job_id == job_id).options(
            selectinload(Finding.indicators)
        ).order_by(Finding.created_at.asc())
        return list(self.session.scalars(stmt).all())
