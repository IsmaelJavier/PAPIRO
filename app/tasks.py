import httpx

from app.db import db_session
from app.models import JobStatus, RunStatus
from app.repository import Repository
from app.sources.github import GitHubRateLimitError, GitHubSource
from app.sources.wikidata import WikidataRateLimitError, WikidataSource
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

        sources = [GitHubSource(), WikidataSource()]
        total_findings = 0
        successful_sources = 0
        failed_sources = 0
        partial_sources = 0
        source_errors: list[str] = []

        for source in sources:
            run = repo.create_run(
                job.id,
                source.module_name,
                source.name,
                job.input_value,
            )

            try:
                result = source.search_person_name(job.input_value)
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

        repo.mark_job_finished(job, final_status, error)
        return {
            "job_id": job.id,
            "status": final_status.value,
            "findings": total_findings,
            "successful_sources": successful_sources,
            "partial_sources": partial_sources,
            "failed_sources": failed_sources,
            "errors": source_errors,
        }
