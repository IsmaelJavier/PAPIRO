from datetime import datetime
from pydantic import BaseModel, Field


class IngestNameRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str


class IndicatorResponse(BaseModel):
    id: str
    indicator_type: str
    value: str
    normalized_value: str
    provenance_field: str


class FindingResponse(BaseModel):
    id: str
    module: str
    source: str
    source_url: str
    input_value: str
    input_type: str
    finding_type: str
    value: str
    confidence: float
    relevance_reason: str
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
    module_runs: list[ModuleRunResponse]
