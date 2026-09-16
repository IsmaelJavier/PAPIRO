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
    Entity,
    EntityFinding,
    EntityType,
    Relationship,
    RelationshipAssessment,
    RelationshipEvidence,
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


    def create_entity(
        self,
        job_id: str,
        label: str,
        *,
        entity_type: EntityType = EntityType.person_candidate,
        description: str | None = None,
        finding_ids: list[str] | None = None,
        finding_role: str | None = "evidencia",
    ) -> Entity:
        entity = Entity(
            job_id=job_id,
            label=label.strip(),
            entity_type=entity_type,
            description=description,
        )
        self.session.add(entity)
        self.session.flush()

        # Entity creation can atomically include the findings selected by the
        # investigator. No identity conclusion is inferred here.
        unique_ids = list(dict.fromkeys(finding_ids or []))
        if unique_ids:
            findings = list(
                self.session.scalars(
                    select(Finding).where(
                        Finding.job_id == job_id,
                        Finding.id.in_(unique_ids),
                    )
                ).all()
            )
            found_ids = {row.id for row in findings}
            missing = [fid for fid in unique_ids if fid not in found_ids]
            if missing:
                raise ValueError(
                    "all selected findings must belong to the job; missing: "
                    + ", ".join(missing)
                )
            for finding in findings:
                self.attach_finding_to_entity(
                    entity, finding, role=finding_role
                )

        return entity

    def update_entity(
        self,
        entity: Entity,
        *,
        label: str | None = None,
        description: str | None = None,
    ) -> Entity:
        if label is not None:
            entity.label = label.strip()
        if description is not None:
            entity.description = description
        entity.updated_at = utcnow()
        self.session.flush()
        return entity

    def get_entities(self, job_id: str) -> list[Entity]:
        stmt = (
            select(Entity)
            .where(Entity.job_id == job_id)
            .options(
                selectinload(Entity.findings).selectinload(EntityFinding.finding).selectinload(
                    Finding.indicators
                ),
            )
            .order_by(Entity.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_entity(self, entity_id: str) -> Entity | None:
        stmt = (
            select(Entity)
            .where(Entity.id == entity_id)
            .options(
                selectinload(Entity.findings).selectinload(EntityFinding.finding).selectinload(
                    Finding.indicators
                ),
                selectinload(Entity.relationships_as_a),
                selectinload(Entity.relationships_as_b),
            )
        )
        return self.session.scalar(stmt)

    def attach_finding_to_entity(
        self,
        entity: Entity,
        finding: Finding,
        *,
        role: str | None = None,
    ) -> EntityFinding:
        if entity.job_id != finding.job_id:
            raise ValueError("entity and finding must belong to the same job")

        existing = self.session.scalar(
            select(EntityFinding).where(
                EntityFinding.entity_id == entity.id,
                EntityFinding.finding_id == finding.id,
            )
        )
        if existing:
            if role is not None:
                existing.role = role
            entity.updated_at = utcnow()
            self.session.flush()
            return existing

        membership = EntityFinding(
            entity_id=entity.id, finding_id=finding.id, role=role
        )
        self.session.add(membership)
        entity.updated_at = utcnow()
        self.session.flush()
        return membership

    def create_relationship(
        self,
        job_id: str,
        entity_a: Entity,
        entity_b: Entity,
        *,
        relationship_type: str,
        basis: str,
        assessment: RelationshipAssessment = RelationshipAssessment.undetermined,
        correlation_id: str | None = None,
        finding_a_id: str | None = None,
        finding_b_id: str | None = None,
    ) -> Relationship:
        if entity_a.job_id != job_id or entity_b.job_id != job_id:
            raise ValueError("entities must belong to the same job")
        if entity_a.id == entity_b.id:
            raise ValueError("an entity cannot relate to itself")

        first, second = sorted((entity_a.id, entity_b.id))
        existing = self.session.scalar(
            select(Relationship).where(
                Relationship.job_id == job_id,
                Relationship.entity_a_id == first,
                Relationship.entity_b_id == second,
                Relationship.relationship_type == relationship_type,
            )
        )
        if existing:
            return existing

        relationship = Relationship(
            job_id=job_id,
            entity_a_id=first,
            entity_b_id=second,
            relationship_type=relationship_type,
            basis=basis,
            assessment=assessment,
        )
        self.session.add(relationship)
        self.session.flush()

        if correlation_id is not None:
            self.session.add(
                RelationshipEvidence(
                    relationship_id=relationship.id,
                    correlation_id=correlation_id,
                    finding_a_id=finding_a_id,
                    finding_b_id=finding_b_id,
                )
            )
            self.session.flush()
        return relationship

    def update_relationship(
        self,
        relationship: Relationship,
        *,
        relationship_type: str | None = None,
        basis: str | None = None,
    ) -> Relationship:
        if relationship_type is not None:
            relationship.relationship_type = relationship_type.strip()
        if basis is not None:
            relationship.basis = basis.strip()
        self.session.flush()
        return relationship

    def get_relationships(self, job_id: str) -> list[Relationship]:
        stmt = (
            select(Relationship)
            .where(Relationship.job_id == job_id)
            .options(
                selectinload(Relationship.entity_a),
                selectinload(Relationship.entity_b),
                selectinload(Relationship.evidence),
            )
            .order_by(Relationship.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_graph(self, job_id: str) -> dict:
        """Return a traceable graph projection for investigator exploration.

        The projection exposes findings, indicators, deterministic correlations,
        investigator-managed entities and relationships. It does not infer
        identity or create entities automatically.
        """
        findings = self.get_findings(job_id)
        correlations = self.get_correlations(job_id)
        entities = self.get_entities(job_id)
        relationships = self.get_relationships(job_id)

        nodes: list[dict] = []
        edges: list[dict] = []

        for finding in findings:
            nodes.append({
                "id": f"finding:{finding.id}",
                "node_type": "finding",
                "label": finding.value,
                "source": finding.source,
                "finding_type": finding.finding_type,
                "assessment": finding.identity_assessment.value,
                "relevance": finding.relevance_assessment.value,
                "source_url": finding.source_url,
                "evidence_strength": finding.evidence_strength,
            })
            for indicator in finding.indicators:
                indicator_id = f"indicator:{indicator.id}"
                nodes.append({
                    "id": indicator_id,
                    "node_type": "indicator",
                    "label": indicator.value,
                    "indicator_type": indicator.indicator_type,
                    "normalized_value": indicator.normalized_value,
                    "source": finding.source,
                    "provenance_field": indicator.provenance_field,
                })
                edges.append({
                    "id": f"edge:finding-indicator:{indicator.id}",
                    "edge_type": "contains_indicator",
                    "source": f"finding:{finding.id}",
                    "target": indicator_id,
                    "basis": indicator.provenance_field,
                })

        for correlation in correlations:
            edges.append({
                "id": f"correlation:{correlation.id}",
                "edge_type": "correlation",
                "source": f"finding:{correlation.finding_a_id}",
                "target": f"finding:{correlation.finding_b_id}",
                "correlation_id": correlation.id,
                "correlation_type": correlation.correlation_type,
                "basis": correlation.basis,
                "assessment": correlation.assessment.value,
            })

        for entity in entities:
            nodes.append({
                "id": f"entity:{entity.id}",
                "node_type": "entity",
                "label": entity.label,
                "entity_type": entity.entity_type.value,
                "description": entity.description,
            })
            for membership in entity.findings:
                edges.append({
                    "id": f"edge:entity-finding:{membership.id}",
                    "edge_type": "entity_membership",
                    "source": f"entity:{entity.id}",
                    "target": f"finding:{membership.finding_id}",
                    "role": membership.role,
                })

        for relationship in relationships:
            edges.append({
                "id": f"relationship:{relationship.id}",
                "edge_type": "relationship",
                "source": f"entity:{relationship.entity_a_id}",
                "target": f"entity:{relationship.entity_b_id}",
                "relationship_id": relationship.id,
                "relationship_type": relationship.relationship_type,
                "basis": relationship.basis,
                "assessment": relationship.assessment.value,
            })

        return {
            "job_id": job_id,
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "findings": len(findings),
                "indicators": sum(len(f.indicators) for f in findings),
                "correlations": len(correlations),
                "entities": len(entities),
                "relationships": len(relationships),
            },
        }

    def assess_relationship(
        self,
        relationship: Relationship,
        *,
        assessment: RelationshipAssessment | None = None,
        assessment_note: str | None = None,
        update_note: bool = False,
    ) -> Relationship:
        if assessment is not None:
            relationship.assessment = assessment
        if update_note:
            relationship.assessment_note = assessment_note
        relationship.assessment_updated_at = utcnow()
        self.session.flush()
        return relationship

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