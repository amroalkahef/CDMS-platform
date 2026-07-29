from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.constants import CIRCULAR_FREQUENCIES, CIRCULAR_STATUSES, DECISION_STATUSES, DEPARTMENTS
from app.errors import DomainError


class DraftRequest(BaseModel):
    task_type: str = Field(examples=["generate_circular", "generate_decision", "summarize"])
    user_prompt: str
    doc_type_filter: str | None = None
    required_sections: list[str] = []
    # UI locale ("en"/"ar") from the web console, so the Authoring Agent can
    # be told explicitly what language to draft in instead of guessing from
    # user_prompt/context alone.
    language: str | None = None


class DraftResponse(BaseModel):
    task_type: str
    draft: str
    references: list[dict]
    confidence: float
    validation_issues: list[dict]
    retrieved_docs: list[dict]
    trace: list[dict]


class SearchResponse(BaseModel):
    query: str
    results: list[dict]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    language: str | None = None


class IngestRequest(BaseModel):
    title: str
    doc_type: str = "general"
    source: str = "manual"
    content: str


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int


class ExecuteRequest(BaseModel):
    entity_type: str = Field(examples=["circular", "decision"])
    title: str
    content: str
    references: list[dict] = []
    created_by: str = "dev-user"


class ExecuteResponse(BaseModel):
    entity_id: str
    entity_type: str
    status: str
    workflow_id: str | None = None


class PublishRequest(BaseModel):
    entity_type: str
    entity_id: str
    requested_by: str
    title: str


class PublishResponse(BaseModel):
    entity_id: str
    entity_type: str
    status: str
    version: int


class VersionOut(BaseModel):
    version: int
    title: str
    content: str
    status: str
    created_by: str
    created_at: str


class VersionsResponse(BaseModel):
    entity_type: str
    entity_id: str
    versions: list[VersionOut]


class CircularCreate(BaseModel):
    title: str
    content: str
    department: str = "Administration"
    frequency: str = "One-Time"
    publication_date: date | None = None
    status: str = "draft"
    references: list[dict] = []
    created_by: str = "dev-user"

    @field_validator("department")
    @classmethod
    def _valid_department(cls, v: str) -> str:
        if v not in DEPARTMENTS:
            raise DomainError("invalid_department", allowed=", ".join(DEPARTMENTS))
        return v

    @field_validator("frequency")
    @classmethod
    def _valid_frequency(cls, v: str) -> str:
        if v not in CIRCULAR_FREQUENCIES:
            raise DomainError("invalid_frequency", allowed=", ".join(CIRCULAR_FREQUENCIES))
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in CIRCULAR_STATUSES:
            raise DomainError("invalid_status", allowed=", ".join(CIRCULAR_STATUSES))
        return v


class CircularUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    department: str | None = None
    frequency: str | None = None
    publication_date: date | None = None
    status: str | None = None
    updated_by: str = "dev-user"


class CircularOut(BaseModel):
    id: str
    entity_type: str = "circular"
    circular_number: str | None = None
    title: str
    content: str
    department: str
    frequency: str
    publication_date: str | None
    status: str
    version: int
    created_by: str
    references: list[dict]
    created_at: str
    published_at: str | None
    workflow_id: str | None = None


class DecisionCreate(BaseModel):
    title: str
    content: str
    department: str = "Administration"
    effective_date: date | None = None
    status: str = "draft"
    references: list[dict] = []
    created_by: str = "dev-user"

    @field_validator("department")
    @classmethod
    def _valid_department(cls, v: str) -> str:
        if v not in DEPARTMENTS:
            raise DomainError("invalid_department", allowed=", ".join(DEPARTMENTS))
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in DECISION_STATUSES:
            raise DomainError("invalid_status", allowed=", ".join(DECISION_STATUSES))
        return v


class DecisionUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    department: str | None = None
    effective_date: date | None = None
    status: str | None = None
    updated_by: str = "dev-user"


class DecisionOut(BaseModel):
    id: str
    entity_type: str = "decision"
    decision_number: str | None
    title: str
    content: str
    department: str
    effective_date: str | None
    status: str
    version: int
    created_by: str
    references: list[dict]
    created_at: str
    published_at: str | None
    workflow_id: str | None = None


class SimilarityCheckRequest(BaseModel):
    entity_type: str
    title: str
    content: str
    exclude_id: str | None = None


class SimilarityHit(BaseModel):
    id: str
    title: str
    department: str
    status: str
    similarity: float
    verdict: str  # "duplicate" | "related" | "different" | "unknown"
    explanation: str | None = None
    is_likely_duplicate: bool


class SimilarityCheckResponse(BaseModel):
    results: list[SimilarityHit]


class ActivityItem(BaseModel):
    action: str
    detail: str
    user: str
    timestamp: str


class UpcomingDeadline(BaseModel):
    id: str
    title: str
    department: str
    publication_date: str


class StatsResponse(BaseModel):
    total_circulars: int
    total_decisions: int
    pending_drafts: int
    published: int
    recent_activity: list[ActivityItem]
    upcoming_deadlines: list[UpcomingDeadline]
