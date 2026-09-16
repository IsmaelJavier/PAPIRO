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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
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


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    input_value: Mapped[str] = mapped_column(Text, nullable=False)
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

    findings = relationship(
        "Finding",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    runs = relationship(
        "ModuleRun",
        back_populates="job",
        cascade="all, delete-orphan",
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

    job = relationship(
        "Job",
        back_populates="runs",
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
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    relevance_reason: Mapped[str] = mapped_column(
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
        ),
        nullable=False,
        default=IdentityAssessment.undetermined,
    )

    relevance_assessment: Mapped[RelevanceAssessment] = mapped_column(
        Enum(
            RelevanceAssessment,
            native_enum=False,
            length=32,
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

    job = relationship(
        "Job",
        back_populates="findings",
    )

    indicators = relationship(
        "Indicator",
        back_populates="finding",
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

    finding = relationship(
        "Finding",
        back_populates="indicators",
    )