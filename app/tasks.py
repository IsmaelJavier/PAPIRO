import httpx

from app.db import db_session
from app.models import JobStatus, RunStatus
from app.repository import Repository
from app.sources.github import GitHubRateLimitError, GitHubSource
from app.worker import celery_app


@celery_app.task(name="app.tasks.process_person_name_job")
def process_person_name_job(job_id: str):
    with db_session() as session:
        repo = Repository(session)
        job = repo.get_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "missing"}

        repo.mark_job_running(job)
        session.flush()

        source = GitHubSource()
        run = repo.create_run(job.id, source.module_name, source.name, job.input_value)

        try:
            result = source.search_person_name(job.input_value)
            for finding, indicators in result.findings:
                repo.add_finding(job.id, finding, indicators)

            repo.finish_run(run, RunStatus.success, result.http_status,
                            rate_limit_remaining=result.rate_limit_remaining)
            repo.mark_job_finished(job, JobStatus.completed)
            return {"job_id": job.id, "status": "completed", "findings": len(result.findings)}

        except GitHubRateLimitError as exc:
            repo.finish_run(run, RunStatus.rate_limited, error=str(exc))
            repo.mark_job_finished(job, JobStatus.partial, str(exc))
            return {"job_id": job.id, "status": "partial", "error": str(exc)}

        except httpx.TimeoutException as exc:
            repo.finish_run(run, RunStatus.timeout, error=str(exc))
            repo.mark_job_finished(job, JobStatus.failed, str(exc))
            return {"job_id": job.id, "status": "failed", "error": str(exc)}

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            repo.finish_run(run, RunStatus.failed, http_status=status, error=str(exc))
            repo.mark_job_finished(job, JobStatus.failed, str(exc))
            return {"job_id": job.id, "status": "failed", "error": str(exc)}

        except Exception as exc:
            repo.finish_run(run, RunStatus.failed, error=str(exc))
            repo.mark_job_finished(job, JobStatus.failed, str(exc))
            raise
