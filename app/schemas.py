from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models import (
    IdentityAssessment,
    RelevanceAssessment,
    CorrelationAssessment,
    EntityType,
    RelationshipAssessment,
)


class IngestNameRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )
    organization_id: str | None = None


class InvestigationCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=10000)
    organization_id: str | None = None


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
    is_owner: bool = False

    input_value: str
    investigation_title: str | None = None
    notes: str | None = None
    input_type: str

    status: str
    error: str | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    finding_count: int
    correlation_count: int

    module_runs: list[ModuleRunResponse]

class EntityCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    entity_type: EntityType = EntityType.person_candidate
    description: str | None = Field(default=None, max_length=2000)
    # Optional evidence selected by the investigator at creation time.
    # The API validates that every finding belongs to the same job.
    finding_ids: list[str] = Field(default_factory=list, max_length=100)


class EntityUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one entity field must be provided")
        return self


class EntityFindingAttachRequest(BaseModel):
    finding_id: str
    role: str | None = Field(default=None, max_length=100)


class EntityFindingResponse(BaseModel):
    id: str
    finding_id: str
    role: str | None


class EntityResponse(BaseModel):
    id: str
    job_id: str
    label: str
    entity_type: EntityType
    description: str | None
    created_at: datetime
    updated_at: datetime
    findings: list[EntityFindingResponse]


class RelationshipCreateRequest(BaseModel):
    entity_a_id: str
    entity_b_id: str
    relationship_type: str = Field(min_length=1, max_length=64)
    basis: str = Field(min_length=1, max_length=4000)
    assessment: RelationshipAssessment = RelationshipAssessment.undetermined
    correlation_id: str | None = None
    finding_a_id: str | None = None
    finding_b_id: str | None = None


class RelationshipUpdateRequest(BaseModel):
    relationship_type: str | None = Field(default=None, min_length=1, max_length=64)
    basis: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one relationship field must be provided")
        return self


class ManualNameSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)


class RelationshipAssessmentRequest(BaseModel):
    assessment: RelationshipAssessment | None = None
    assessment_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one relationship assessment field must be provided")
        return self


class RelationshipResponse(BaseModel):
    id: str
    job_id: str
    entity_a_id: str
    entity_b_id: str
    relationship_type: str
    basis: str
    assessment: RelationshipAssessment
    assessment_note: str | None
    assessment_updated_at: datetime | None
    created_at: datetime
    evidence: list[dict]


class ProfileResponse(BaseModel):
    id: str
    job_id: str
    label: str
    entity_type: EntityType
    description: str | None
    findings: list[FindingResponse]
    indicators: list[IndicatorResponse]
    relationships: list[RelationshipResponse]


class GraphNodeResponse(BaseModel):
    id: str
    node_type: str
    label: str
    source: str | None = None
    finding_type: str | None = None
    assessment: str | None = None
    relevance: str | None = None
    source_url: str | None = None
    evidence_strength: float | None = None
    indicator_type: str | None = None
    normalized_value: str | None = None
    provenance_field: str | None = None
    entity_type: str | None = None
    description: str | None = None


class GraphEdgeResponse(BaseModel):
    id: str
    edge_type: str
    source: str
    target: str
    basis: str | None = None
    role: str | None = None
    correlation_id: str | None = None
    correlation_type: str | None = None
    assessment: str | None = None
    relationship_id: str | None = None
    relationship_type: str | None = None


class GraphResponse(BaseModel):
    job_id: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    summary: dict[str, int]
