import httpx
from datetime import datetime, timezone
from sqlalchemy import or_, select

from app.db import db_session
from app.models import InvestigationCheckpoint, Job, JobStatus, RunStatus
from app.repository import Repository
from app.sources.github import GitHubRateLimitError
from app.sources.wikidata import WikidataRateLimitError
from app.sources.registry import get_person_name_sources
from app.worker import celery_app


def _capture_checkpoint_guard(session, job_id: str, requested_at=None, requested_checkpoint_id=None):
    """Keep the enqueue time so a queued task can detect a session discarded before it started."""
    started_at = (
        datetime.fromisoformat(requested_at)
        if requested_at else datetime.now(timezone.utc)
    )
    active_id = session.query(InvestigationCheckpoint.id).filter(
        InvestigationCheckpoint.job_id == job_id,
        InvestigationCheckpoint.status == "active",
    ).order_by(InvestigationCheckpoint.created_at.desc()).first()
    return requested_checkpoint_id or (active_id[0] if active_id else None), started_at


def _discard_requested(session, job_id: str, checkpoint_id, started_at) -> bool:
    """Detect discard of the task's session or any session opened after it was queued."""
    session_scope = [InvestigationCheckpoint.created_at >= started_at]
    if checkpoint_id:
        session_scope.append(InvestigationCheckpoint.id == checkpoint_id)
    discarded_session = session.query(InvestigationCheckpoint.id).filter(
        InvestigationCheckpoint.job_id == job_id,
        InvestigationCheckpoint.status.in_(("restoring", "discarded")),
        or_(*session_scope),
    )
    return discarded_session.first() is not None




@celery_app.task(name="app.tasks.process_person_name_job")
def process_person_name_job(job_id: str, requested_at: str | None = None, requested_checkpoint_id: str | None = None):
    with db_session() as session:
        # Serialize worker writes with discard/restore, which locks the same job row.
        session.execute(select(Job.id).where(Job.id == job_id).with_for_update()).first()
        checkpoint_id, task_started_at = _capture_checkpoint_guard(
            session, job_id, requested_at, requested_checkpoint_id
        )
        repo = Repository(session)
        job = repo.get_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "missing"}

        repo.mark_job_running(job)
        session.flush()

        sources = get_person_name_sources()
        total_findings = 0
        successful_sources = 0
        failed_sources = 0
        partial_sources = 0
        source_errors: list[str] = []

        for source in sources:
            if _discard_requested(session, job_id, checkpoint_id, task_started_at):
                session.rollback()
                return {"job_id": job_id, "status": "discarded", "cancelled": True}
            run = repo.create_run(
                job.id,
                source.module_name,
                source.name,
                job.input_value,
            )

            try:
                result = source.search_person_name(job.input_value)
                if _discard_requested(session, job_id, checkpoint_id, task_started_at):
                    session.rollback()
                    return {"job_id": job_id, "status": "discarded", "cancelled": True}
                for finding, indicators in result.findings:
                    repo.add_finding(job.id, finding, indicators)

                total_findings += len(result.findings)
                successful_sources += 1
                repo.finish_run(
                    run,
                    RunStatus.success,
                    result.http_status,
                    rate_limit_remaining=result.rate_limit_remaining,
                )

            except (GitHubRateLimitError, WikidataRateLimitError) as exc:
                partial_sources += 1
                source_errors.append(f"{source.name}: {exc}")
                repo.finish_run(
                    run,
                    RunStatus.rate_limited,
                    error=str(exc),
                )

            except httpx.TimeoutException as exc:
                failed_sources += 1
                source_errors.append(f"{source.name}: {exc}")
                repo.finish_run(
                    run,
                    RunStatus.timeout,
                    error=str(exc),
                )

            except httpx.HTTPStatusError as exc:
                failed_sources += 1
                status = exc.response.status_code if exc.response is not None else None
                source_errors.append(f"{source.name}: {exc}")
                repo.finish_run(
                    run,
                    RunStatus.failed,
                    http_status=status,
                    error=str(exc),
                )

            except Exception as exc:
                failed_sources += 1
                source_errors.append(f"{source.name}: {exc}")
                repo.finish_run(
                    run,
                    RunStatus.failed,
                    error=str(exc),
                )

        if successful_sources == len(sources):
            final_status = JobStatus.completed
            error = None
        elif successful_sources > 0:
            final_status = JobStatus.partial
            error = "; ".join(source_errors)
        else:
            final_status = JobStatus.failed
            error = "; ".join(source_errors)

        if _discard_requested(session, job_id, checkpoint_id, task_started_at):
            session.rollback()
            return {"job_id": job_id, "status": "discarded", "cancelled": True}

        correlation_count = 0
        if total_findings > 1:
            correlations = repo.correlate_job(job.id)
            correlation_count = len(correlations)

        repo.mark_job_finished(job, final_status, error)
        return {
            "job_id": job.id,
            "status": final_status.value,
            "findings": total_findings,
            "correlations": correlation_count,
            "successful_sources": successful_sources,
            "partial_sources": partial_sources,
            "failed_sources": failed_sources,
            "errors": source_errors,
        }


@celery_app.task(name="app.tasks.process_manual_person_name_search")
def process_manual_person_name_search(
    job_id: str, query: str, requested_at: str | None = None,
    requested_checkpoint_id: str | None = None,
):
    """Run the configured person-name sources for an investigator-entered query.

    This is deliberately additive: findings are deduplicated against the job's
    existing evidence and no prior assessment/entity is changed.
    """
    with db_session() as session:
        # Serialize worker writes with discard/restore, which locks the same job row.
        session.execute(select(Job.id).where(Job.id == job_id).with_for_update()).first()
        checkpoint_id, task_started_at = _capture_checkpoint_guard(
            session, job_id, requested_at, requested_checkpoint_id
        )
        repo = Repository(session)
        job = repo.get_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "missing", "query": query}

        sources = get_person_name_sources()
        added_findings = 0
        successful_sources = 0
        errors: list[str] = []

        for source in sources:
            if _discard_requested(session, job_id, checkpoint_id, task_started_at):
                session.rollback()
                return {"job_id": job_id, "query": query, "status": "discarded", "cancelled": True}
            run = repo.create_run(job.id, source.module_name, source.name, query)
            try:
                # Sources expose the same contract; temporarily build the
                # canonical input through the source's public name-search API.
                result = source.search_person_name(query)
                if _discard_requested(session, job_id, checkpoint_id, task_started_at):
                    session.rollback()
                    return {"job_id": job_id, "query": query, "status": "discarded", "cancelled": True}
                before = len(repo.get_findings(job.id))
                for finding, indicators in result.findings:
                    repo.add_finding(job.id, finding, indicators)
                after = len(repo.get_findings(job.id))
                added_findings += max(0, after - before)
                successful_sources += 1
                repo.finish_run(run, RunStatus.success, result.http_status,
                                rate_limit_remaining=result.rate_limit_remaining)
            except (GitHubRateLimitError, WikidataRateLimitError) as exc:
                errors.append(f"{source.name}: {exc}")
                repo.finish_run(run, RunStatus.rate_limited, error=str(exc))
            except httpx.TimeoutException as exc:
                errors.append(f"{source.name}: {exc}")
                repo.finish_run(run, RunStatus.timeout, error=str(exc))
            except httpx.HTTPStatusError as exc:
                errors.append(f"{source.name}: {exc}")
                status = exc.response.status_code if exc.response is not None else None
                repo.finish_run(run, RunStatus.failed, http_status=status, error=str(exc))
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")
                repo.finish_run(run, RunStatus.failed, error=str(exc))

        if _discard_requested(session, job_id, checkpoint_id, task_started_at):
            session.rollback()
            return {"job_id": job_id, "query": query, "status": "discarded", "cancelled": True}
        correlation_count = len(repo.correlate_job(job.id)) if len(repo.get_findings(job.id)) > 1 else 0
        return {
            "job_id": job.id,
            "query": query,
            "status": "completed" if successful_sources == len(sources) else "partial",
            "added_findings": added_findings,
            "correlations": correlation_count,
            "errors": errors,
        }
