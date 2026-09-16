from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain import (
    CanonicalFinding,
    ExtractedIndicator,
)
from app.models import (
    Correlation,
    CorrelationAssessment,
    CorrelationEvidence,
    Finding,
    IdentityAssessment,
    Indicator,
    Job,
    JobStatus,
    ModuleRun,
    RelevanceAssessment,
    RunStatus,
)


def utcnow():
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_job(
        self,
        input_value: str,
        input_type: str,
    ) -> Job:
        job = Job(
            input_value=input_value,
            input_type=input_type,
            status=JobStatus.queued,
        )

        self.session.add(job)
        self.session.flush()

        return job

    def get_job(
        self,
        job_id: str,
    ) -> Job | None:
        stmt = (
            select(Job)
            .where(Job.id == job_id)
            .options(
                selectinload(Job.runs)
            )
        )

        return self.session.scalar(stmt)

    def mark_job_running(
        self,
        job: Job,
    ):
        job.status = JobStatus.running
        job.started_at = utcnow()
        job.error = None

    def mark_job_finished(
        self,
        job: Job,
        status: JobStatus,
        error: str | None = None,
    ):
        job.status = status
        job.completed_at = utcnow()
        job.error = error

    def create_run(
        self,
        job_id: str,
        module: str,
        source: str,
        query: str,
    ) -> ModuleRun:
        run = ModuleRun(
            job_id=job_id,
            module=module,
            source=source,
            query=query,
            status=RunStatus.success,
            started_at=utcnow(),
        )

        self.session.add(run)
        self.session.flush()

        return run

    def finish_run(
        self,
        run: ModuleRun,
        status: RunStatus,
        http_status: int | None = None,
        error: str | None = None,
        rate_limit_remaining: int | None = None,
    ):
        run.status = status
        run.http_status = http_status
        run.error = error
        run.rate_limit_remaining = rate_limit_remaining
        run.finished_at = utcnow()

    def add_finding(
        self,
        job_id: str,
        finding: CanonicalFinding,
        indicators: list[ExtractedIndicator],
    ) -> Finding:
        existing = self.session.scalar(
            select(Finding).where(
                Finding.job_id == job_id,
                Finding.dedupe_key == finding.dedupe_key,
            )
        )

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
            evidence_strength=finding.evidence_strength,
            match_reason=finding.match_reason,
            dedupe_key=finding.dedupe_key,
            raw_evidence=finding.raw_evidence,

            # Explicit defaults are useful here even though the model
            # also defines defaults. Collection never decides identity.
            identity_assessment=IdentityAssessment.undetermined,
            relevance_assessment=RelevanceAssessment.undetermined,
        )

        self.session.add(row)
        self.session.flush()

        seen: set[tuple[str, str]] = set()

        for indicator in indicators:
            key = (
                indicator.indicator_type,
                indicator.normalized_value,
            )

            if key in seen:
                continue

            seen.add(key)

            self.session.add(
                Indicator(
                    finding_id=row.id,
                    indicator_type=indicator.indicator_type,
                    value=indicator.value,
                    normalized_value=indicator.normalized_value,
                    provenance_field=indicator.provenance_field,
                )
            )

        self.session.flush()

        return row

    def get_finding(
        self,
        finding_id: str,
    ) -> Finding | None:
        stmt = (
            select(Finding)
            .where(Finding.id == finding_id)
            .options(
                selectinload(Finding.indicators)
            )
        )

        return self.session.scalar(stmt)

    def get_findings(
        self,
        job_id: str,
    ) -> list[Finding]:
        stmt = (
            select(Finding)
            .where(Finding.job_id == job_id)
            .options(
                selectinload(Finding.indicators)
            )
            .order_by(Finding.created_at.asc())
        )

        return list(
            self.session.scalars(stmt).all()
        )

    @staticmethod
    def _correlation_type(indicator_type: str) -> str | None:
        """Return the correlation relation supported by an indicator type."""
        return {
            "email": "shared_email",
            "phone": "shared_phone",
            "username": "shared_username",
            "url": "shared_url",
            "domain": "shared_domain",
            "organization": "shared_organization",
            "location": "shared_location",
        }.get(indicator_type)

    def correlate_job(self, job_id: str) -> list[Correlation]:
        """Create deterministic cross-source correlations for a completed job.

        Only exact normalized indicator matches are used. The input name alone
        is never treated as correlation evidence, and correlations do not
        assert that two findings represent the same person.
        """
        findings = self.get_findings(job_id)
        correlations: dict[tuple[str, str], Correlation] = {}

        for i, finding_a in enumerate(findings):
            for finding_b in findings[i + 1:]:
                if finding_a.source == finding_b.source:
                    continue

                matches: list[tuple[Indicator, Indicator, str]] = []
                for indicator_a in finding_a.indicators:
                    ctype = self._correlation_type(
                        indicator_a.indicator_type
                    )
                    if not ctype or not indicator_a.normalized_value:
                        continue

                    for indicator_b in finding_b.indicators:
                        if (
                            indicator_a.indicator_type
                            != indicator_b.indicator_type
                            or indicator_a.normalized_value
                            != indicator_b.normalized_value
                        ):
                            continue
                        matches.append((indicator_a, indicator_b, ctype))

                if not matches:
                    continue

                # One correlation per finding pair. If several indicators
                # support it, preserve all of them as correlation evidence.
                if finding_a.id <= finding_b.id:
                    first_finding, second_finding = finding_a, finding_b
                    ordered_matches = matches
                else:
                    first_finding, second_finding = finding_b, finding_a
                    ordered_matches = [
                        (indicator_b, indicator_a, ctype)
                        for indicator_a, indicator_b, ctype in matches
                    ]

                pair = (first_finding.id, second_finding.id)
                existing = self.session.scalar(
                    select(Correlation).where(
                        Correlation.job_id == job_id,
                        Correlation.finding_a_id == pair[0],
                        Correlation.finding_b_id == pair[1],
                    )
                )
                if existing:
                    correlations[pair] = existing
                    continue

                correlation = Correlation(
                    job_id=job_id,
                    finding_a_id=pair[0],
                    finding_b_id=pair[1],
                    correlation_type=matches[0][2],
                    basis="; ".join(
                        sorted({
                            f"{ctype}:{a.normalized_value}"
                            for a, b, ctype in ordered_matches
                        })
                    ),
                    assessment=CorrelationAssessment.undetermined,
                )
                self.session.add(correlation)
                self.session.flush()

                for indicator_a, indicator_b, _ in ordered_matches:
                    self.session.add(
                        CorrelationEvidence(
                            correlation_id=correlation.id,
                            indicator_a_id=indicator_a.id,
                            indicator_b_id=indicator_b.id,
                        )
                    )

                correlations[pair] = correlation

        self.session.flush()
        return list(correlations.values())

    def get_correlations(
        self,
        job_id: str,
    ) -> list[Correlation]:
        stmt = (
            select(Correlation)
            .where(Correlation.job_id == job_id)
            .options(
                selectinload(Correlation.finding_a).selectinload(
                    Finding.indicators
                ),
                selectinload(Correlation.finding_b).selectinload(
                    Finding.indicators
                ),
                selectinload(Correlation.evidence).selectinload(
                    CorrelationEvidence.indicator_a
                ),
                selectinload(Correlation.evidence).selectinload(
                    CorrelationEvidence.indicator_b
                ),
            )
            .order_by(Correlation.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def assess_correlation(
        self,
        correlation: Correlation,
        *,
        assessment: CorrelationAssessment | None = None,
        assessment_note: str | None = None,
        update_note: bool = False,
    ) -> Correlation:
        if assessment is not None:
            correlation.assessment = assessment
        if update_note:
            correlation.assessment_note = assessment_note
        correlation.assessment_updated_at = utcnow()
        self.session.flush()
        return correlation

    def assess_finding(
        self,
        finding: Finding,
        *,
        identity_assessment: IdentityAssessment | None = None,
        relevance_assessment: RelevanceAssessment | None = None,
        assessment_note: str | None = None,
        update_note: bool = False,
    ) -> Finding:
        """
        Apply investigator assessment without modifying source evidence.

        Identity and relevance are independent dimensions.
        """

        if identity_assessment is not None:
            finding.identity_assessment = identity_assessment

        if relevance_assessment is not None:
            finding.relevance_assessment = relevance_assessment

        if update_note:
            finding.assessment_note = assessment_note

        finding.assessment_updated_at = utcnow()

        self.session.flush()

        return finding