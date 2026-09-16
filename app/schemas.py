from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models import (
    IdentityAssessment,
    RelevanceAssessment,
    CorrelationAssessment,
)


class IngestNameRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str


class IndicatorResponse(BaseModel):
    id: str
    indicator_type: str
    value: str
    normalized_value: str
    provenance_field: str


class FindingAssessmentRequest(BaseModel):
    identity_assessment: IdentityAssessment | None = None
    relevance_assessment: RelevanceAssessment | None = None

    assessment_note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError(
                "at least one assessment field must be provided"
            )

        return self


class CorrelationAssessmentRequest(BaseModel):
    assessment: CorrelationAssessment | None = None
    assessment_note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError(
                "at least one correlation assessment field must be provided"
            )
        return self


class CorrelationEvidenceResponse(BaseModel):
    indicator_a_id: str
    indicator_b_id: str
    indicator_type: str
    normalized_value: str


class CorrelationResponse(BaseModel):
    id: str
    job_id: str
    finding_a_id: str
    finding_b_id: str
    correlation_type: str
    basis: str
    assessment: CorrelationAssessment
    assessment_note: str | None
    assessment_updated_at: datetime | None
    created_at: datetime
    evidence: list[CorrelationEvidenceResponse]


class FindingResponse(BaseModel):
    id: str

    module: str
    source: str
    source_url: str

    input_value: str
    input_type: str

    finding_type: str
    value: str

    evidence_strength: float
    match_reason: str

    identity_assessment: IdentityAssessment
    relevance_assessment: RelevanceAssessment

    assessment_note: str | None
    assessment_updated_at: datetime | None

    raw_evidence: dict

    created_at: datetime

    indicators: list[IndicatorResponse]


class ModuleRunResponse(BaseModel):
    id: str

    module: str
    source: str
    query: str

    status: str

    http_status: int | None
    error: str | None
    rate_limit_remaining: int | None

    started_at: datetime
    finished_at: datetime | None


class JobResponse(BaseModel):
    id: str

    input_value: str
    input_type: str

    status: str
    error: str | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    finding_count: int
    correlation_count: int

    module_runs: list[ModuleRunResponse]