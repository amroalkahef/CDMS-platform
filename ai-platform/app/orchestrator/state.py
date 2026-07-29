from typing import Optional, TypedDict


class RetrievedDoc(TypedDict):
    document_id: str
    title: str
    doc_type: str
    chunk_content: str
    similarity: float


class ValidationIssue(TypedDict):
    severity: str  # "error" | "warning" | "info"
    category: str  # e.g. "missing_section", "hallucination", "citation"
    message: str


class AgentState(TypedDict, total=False):
    task_type: str  # "generate_circular" | "generate_decision" | "summarize"
    user_prompt: str
    doc_type_filter: Optional[str]
    required_sections: list[str]
    language: Optional[str]  # "en" | "ar" | None (unspecified -> infer from user_prompt)

    retrieved_docs: list[RetrievedDoc]
    draft: str
    references: list[dict]
    confidence: float

    validation_issues: list[ValidationIssue]

    trace: list[dict]  # per-node timing/audit breadcrumbs
