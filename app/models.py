import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    draft = "draft"
    queued = "queued"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"


class RunStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    timeout = "timeout"
    rate_limited = "rate_limited"
    skipped = "skipped"


class IdentityAssessment(str, enum.Enum):
    undetermined = "indeterminado"
    belongs = "pertenece"
    does_not_belong = "no_pertenece"


class RelevanceAssessment(str, enum.Enum):
    undetermined = "indeterminado"
    relevant = "relevante"
    not_relevant = "no_relevante"


class UserRole(str, enum.Enum):
    superuser = "superuser"
    investigator = "investigator"
    user = "user"


class MembershipRole(str, enum.Enum):
    entity = "entity"
    investigator = "investigator"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    global_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32,
             values_callable=lambda cls: [item.value for item in cls]),
        nullable=False, default=UserRole.investigator,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    memberships = orm_relationship("OrganizationMembership", back_populates="user", cascade="all, delete-orphan")
    owned_jobs = orm_relationship("Job", back_populates="owner")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    memberships = orm_relationship("OrganizationMembership", back_populates="organization", cascade="all, delete-orphan")
    jobs = orm_relationship("Job", back_populates="organization")


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_organization_membership"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, native_enum=False, length=32,
             values_callable=lambda cls: [item.value for item in cls]),
        nullable=False, default=MembershipRole.investigator,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = orm_relationship("User", back_populates="memberships")
    organization = orm_relationship("Organization", back_populates="memberships")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    input_value: Mapped[str] = mapped_column(Text, nullable=False)
    # Human-readable investigation title is distinct from an actual search query.
    investigation_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_jobs_owner_user"), nullable=True, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT", name="fk_jobs_organization"), nullable=True, index=True
    )
    input_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="person_name",
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus),
        nullable=False,
        default=JobStatus.queued,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    owner = orm_relationship("User", back_populates="owned_jobs")
    organization = orm_relationship("Organization", back_populates="jobs")

    findings = orm_relationship(
        "Finding",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    runs = orm_relationship(
        "ModuleRun",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    correlations = orm_relationship(
        "Correlation",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    entities = orm_relationship(
        "Entity", back_populates="job", cascade="all, delete-orphan"
    )
    relationships = orm_relationship(
        "Relationship", back_populates="job", cascade="all, delete-orphan"
    )


class ModuleRun(Base):
    __tablename__ = "module_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus),
        nullable=False,
    )

    http_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    rate_limit_remaining: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    job = orm_relationship(
        "Job",
        back_populates="runs",
    )


class EntityType(str, enum.Enum):
    person_candidate = "person_candidate"


class RelationshipAssessment(str, enum.Enum):
    undetermined = "indeterminado"
    confirmed = "confirmada"
    discarded = "descartada"


class Entity(Base):
    """Investigator-managed candidate entity within an OSINT job.

    An entity is a reconstruction container, not an automatic identity
    conclusion. Findings may be assigned to it by the investigator.
    """

    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(
            EntityType, native_enum=False, length=32,
            values_callable=lambda enum_class: [m.value for m in enum_class],
        ),
        nullable=False, default=EntityType.person_candidate,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    job = orm_relationship("Job", back_populates="entities")
    findings = orm_relationship(
        "EntityFinding", back_populates="entity", cascade="all, delete-orphan"
    )
    relationships_as_a = orm_relationship(
        "Relationship", foreign_keys="Relationship.entity_a_id",
        back_populates="entity_a", cascade="all, delete-orphan"
    )
    relationships_as_b = orm_relationship(
        "Relationship", foreign_keys="Relationship.entity_b_id",
        back_populates="entity_b", cascade="all, delete-orphan"
    )


class EntityFinding(Base):
    __tablename__ = "entity_findings"
    __table_args__ = (
        UniqueConstraint("entity_id", "finding_id", name="uq_entity_finding"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    entity = orm_relationship("Entity", back_populates="findings")
    finding = orm_relationship("Finding")


class Relationship(Base):
    """Investigator-managed relation between reconstructed entities."""

    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "entity_a_id", "entity_b_id", "relationship_type",
            name="uq_entity_relationship",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_a_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_b_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    assessment: Mapped[RelationshipAssessment] = mapped_column(
        Enum(
            RelationshipAssessment, native_enum=False, length=32,
            values_callable=lambda enum_class: [m.value for m in enum_class],
        ),
        nullable=False, default=RelationshipAssessment.undetermined,
    )
    assessment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job = orm_relationship("Job", back_populates="relationships")
    entity_a = orm_relationship(
        "Entity", foreign_keys=[entity_a_id], back_populates="relationships_as_a"
    )
    entity_b = orm_relationship(
        "Entity", foreign_keys=[entity_b_id], back_populates="relationships_as_b"
    )
    evidence = orm_relationship(
        "RelationshipEvidence", back_populates="relationship",
        cascade="all, delete-orphan"
    )


class RelationshipEvidence(Base):
    __tablename__ = "relationship_evidence"
    __table_args__ = (
        UniqueConstraint(
            "relationship_id", "correlation_id",
            name="uq_relationship_correlation_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    relationship_id: Mapped[str] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    correlation_id: Mapped[str | None] = mapped_column(
        ForeignKey("correlations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    finding_a_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )
    finding_b_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )

    relationship = orm_relationship("Relationship", back_populates="evidence")
    correlation = orm_relationship("Correlation", foreign_keys=[correlation_id])


class CorrelationAssessment(str, enum.Enum):
    undetermined = "indeterminado"
    confirmed = "confirmada"
    discarded = "descartada"


class Correlation(Base):
    """Deterministic association between findings based on shared indicators.

    A correlation is an observed linkage between pieces of evidence. It is
    not an automatic identity conclusion.
    """

    __tablename__ = "correlations"

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "finding_a_id",
            "finding_b_id",
            name="uq_correlation_job_findings",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_a_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_b_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    correlation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    basis: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    assessment: Mapped[CorrelationAssessment] = mapped_column(
        Enum(
            CorrelationAssessment,
            native_enum=False,
            length=32,
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=CorrelationAssessment.undetermined,
    )
    assessment_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    assessment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    job = orm_relationship("Job", back_populates="correlations")
    finding_a = orm_relationship(
        "Finding",
        foreign_keys=[finding_a_id],
        back_populates="correlations_as_a",
    )
    finding_b = orm_relationship(
        "Finding",
        foreign_keys=[finding_b_id],
        back_populates="correlations_as_b",
    )
    evidence = orm_relationship(
        "CorrelationEvidence",
        back_populates="correlation",
        cascade="all, delete-orphan",
    )


class CorrelationEvidence(Base):
    __tablename__ = "correlation_evidence"

    __table_args__ = (
        UniqueConstraint(
            "correlation_id",
            "indicator_a_id",
            "indicator_b_id",
            name="uq_correlation_indicator_pair",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    correlation_id: Mapped[str] = mapped_column(
        ForeignKey("correlations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    indicator_a_id: Mapped[str] = mapped_column(
        ForeignKey("indicators.id", ondelete="CASCADE"),
        nullable=False,
    )
    indicator_b_id: Mapped[str] = mapped_column(
        ForeignKey("indicators.id", ondelete="CASCADE"),
        nullable=False,
    )

    correlation = orm_relationship(
        "Correlation",
        back_populates="evidence",
    )
    indicator_a = orm_relationship(
        "Indicator",
        foreign_keys=[indicator_a_id],
    )
    indicator_b = orm_relationship(
        "Indicator",
        foreign_keys=[indicator_b_id],
    )


class Finding(Base):
    __tablename__ = "findings"

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "dedupe_key",
            name="uq_finding_job_dedupe",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    module: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    input_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    input_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    finding_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # IMPORTANT:
    # This value does NOT represent probability that the profile belongs
    # to the target person. It measures the strength of the observable
    # evidence that motivated the finding.
    evidence_strength: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    match_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    dedupe_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    raw_evidence: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    # Human assessment dimensions.
    #
    # They are deliberately independent. For example:
    #
    # identity_assessment = no_pertenece
    # relevance_assessment = relevante
    #
    # is a valid state.
    identity_assessment: Mapped[IdentityAssessment] = mapped_column(
        Enum(
            IdentityAssessment,
            native_enum=False,
            length=32,
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=IdentityAssessment.undetermined,
    )

    relevance_assessment: Mapped[RelevanceAssessment] = mapped_column(
        Enum(
            RelevanceAssessment,
            native_enum=False,
            length=32,
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=RelevanceAssessment.undetermined,
    )

    assessment_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    assessment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    job = orm_relationship(
        "Job",
        back_populates="findings",
    )

    indicators = orm_relationship(
        "Indicator",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
    correlations_as_a = orm_relationship(
        "Correlation",
        foreign_keys="Correlation.finding_a_id",
        back_populates="finding_a",
        cascade="all, delete-orphan",
    )
    correlations_as_b = orm_relationship(
        "Correlation",
        foreign_keys="Correlation.finding_b_id",
        back_populates="finding_b",
        cascade="all, delete-orphan",
    )


class Indicator(Base):
    __tablename__ = "indicators"

    __table_args__ = (
        UniqueConstraint(
            "finding_id",
            "indicator_type",
            "normalized_value",
            name="uq_indicator_finding_value",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    indicator_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    provenance_field: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    finding = orm_relationship(
        "Finding",
        back_populates="indicators",
    )