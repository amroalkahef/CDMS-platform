from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


DEFAULT_APPROVAL_CHAIN = ["reviewer"]


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str  # "editor" | "reviewer"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class WorkflowCreate(BaseModel):
    entity_type: str
    entity_id: str
    title: str
    requested_by: str = "dev-user"
    approval_chain: list[str] = DEFAULT_APPROVAL_CHAIN


class WorkflowStepOut(BaseModel):
    id: UUID
    step_order: int
    role: str
    status: str
    decided_by: str | None
    decided_at: datetime | None
    comment: str | None

    model_config = {"from_attributes": True}


class WorkflowOut(BaseModel):
    id: UUID
    entity_type: str
    entity_id: str
    title: str
    status: str
    current_step_order: int
    requested_by: str
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepOut] = []

    model_config = {"from_attributes": True}


class WorkflowDecision(BaseModel):
    approve: bool
    comment: str | None = None


class NotificationCreate(BaseModel):
    channel: str = "in_app"
    subject: str
    body: str
    related_workflow_id: str | None = None


class NotificationUpdate(BaseModel):
    status: str  # "read" | "archived"


class NotificationOut(BaseModel):
    id: UUID
    channel: str
    subject: str
    body: str
    status: str
    related_workflow_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DraftProxyRequest(BaseModel):
    task_type: str
    user_prompt: str
    doc_type_filter: str | None = None
    required_sections: list[str] = []
    language: str | None = None


class ChatProxyRequest(BaseModel):
    messages: list[dict]
    language: str | None = None


class ExecuteProxyRequest(BaseModel):
    entity_type: str
    title: str
    content: str
    references: list[dict] = []
    created_by: str = "dev-user"


class IngestProxyRequest(BaseModel):
    title: str
    doc_type: str = "general"
    source: str = "manual"
    content: str


# --- Circulars / Decisions passthrough schemas -----------------------------
# Kept intentionally loose (strict validation — department/status enums —
# happens on the AI Platform, which owns these entities); this layer exists
# so FastAPI can parse/document the request bodies.


class CircularCreateProxy(BaseModel):
    title: str
    content: str
    department: str = "Administration"
    frequency: str = "One-Time"
    publication_date: date | None = None
    status: str = "draft"
    references: list[dict] = []


class CircularUpdateProxy(BaseModel):
    title: str | None = None
    content: str | None = None
    department: str | None = None
    frequency: str | None = None
    publication_date: date | None = None
    status: str | None = None


class DecisionCreateProxy(BaseModel):
    title: str
    content: str
    department: str = "Administration"
    effective_date: date | None = None
    status: str = "draft"
    references: list[dict] = []


class DecisionUpdateProxy(BaseModel):
    title: str | None = None
    content: str | None = None
    department: str | None = None
    effective_date: date | None = None
    status: str | None = None


class SimilarityCheckProxy(BaseModel):
    entity_type: str
    title: str
    content: str
    exclude_id: str | None = None
