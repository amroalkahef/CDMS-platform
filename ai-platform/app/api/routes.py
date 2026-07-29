import json

import openai
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents import chat_agent, execution_agent, validation_agent
from app.constants import CIRCULAR_FREQUENCIES, CIRCULAR_STATUSES, DECISION_STATUSES, DEPARTMENTS
from app.db import get_db
from app.errors import DomainError, error_detail
from app.ingestion import ingest_text
from app.orchestrator import service as orchestrator_service
from app.orchestrator.context_builder import build_context
from app.schemas import (
    ChatRequest,
    CircularCreate,
    CircularOut,
    CircularUpdate,
    DecisionCreate,
    DecisionOut,
    DecisionUpdate,
    DraftRequest,
    DraftResponse,
    ExecuteRequest,
    ExecuteResponse,
    IngestRequest,
    IngestResponse,
    PublishRequest,
    PublishResponse,
    SearchResponse,
    SimilarityCheckRequest,
    SimilarityCheckResponse,
    StatsResponse,
    VersionOut,
    VersionsResponse,
)
from app.stats import get_dashboard_stats
from app.tools.documents import ocr, store_document
from app.tools.rerank import rerank
from app.tools.search import search_documents

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "ai-platform"}


@router.get("/constants")
def constants():
    return {
        "departments": DEPARTMENTS,
        "circular_frequencies": CIRCULAR_FREQUENCIES,
        "circular_statuses": CIRCULAR_STATUSES,
        "decision_statuses": DECISION_STATUSES,
    }


@router.get("/stats", response_model=StatsResponse)
def stats(db: Session = Depends(get_db)):
    return StatsResponse(**get_dashboard_stats(db))


@router.post("/similarity-check", response_model=SimilarityCheckResponse)
def similarity_check(payload: SimilarityCheckRequest, db: Session = Depends(get_db)):
    try:
        results = validation_agent.check_similarity(
            db, payload.entity_type, payload.title, payload.content, exclude_id=payload.exclude_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_detail(exc)) from exc
    return SimilarityCheckResponse(results=results)


@router.get("/circulars", response_model=list[CircularOut])
def list_circulars(status: str | None = None, department: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    return execution_agent.list_entities(db, "circular", status=status, department=department, q=q)


@router.post("/circulars", response_model=CircularOut)
def create_circular(payload: CircularCreate, db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude={"created_by"})
    return execution_agent.create_entity(db, "circular", fields, created_by=payload.created_by)


@router.get("/circulars/{entity_id}", response_model=CircularOut)
def get_circular(entity_id: str, db: Session = Depends(get_db)):
    try:
        return execution_agent.get_entity(db, "circular", entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=error_detail(exc)) from exc


@router.patch("/circulars/{entity_id}", response_model=CircularOut)
def update_circular(entity_id: str, payload: CircularUpdate, db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude={"updated_by"}, exclude_unset=True)
    try:
        return execution_agent.update_entity(db, "circular", entity_id, fields, updated_by=payload.updated_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=error_detail(exc)) from exc


@router.delete("/circulars/{entity_id}", status_code=204)
def delete_circular(entity_id: str, db: Session = Depends(get_db)):
    try:
        execution_agent.delete_entity(db, "circular", entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=error_detail(exc)) from exc


@router.get("/decisions", response_model=list[DecisionOut])
def list_decisions(status: str | None = None, department: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    return execution_agent.list_entities(db, "decision", status=status, department=department, q=q)


@router.post("/decisions", response_model=DecisionOut)
def create_decision(payload: DecisionCreate, db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude={"created_by"})
    return execution_agent.create_entity(db, "decision", fields, created_by=payload.created_by)


@router.get("/decisions/{entity_id}", response_model=DecisionOut)
def get_decision(entity_id: str, db: Session = Depends(get_db)):
    try:
        return execution_agent.get_entity(db, "decision", entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=error_detail(exc)) from exc


@router.patch("/decisions/{entity_id}", response_model=DecisionOut)
def update_decision(entity_id: str, payload: DecisionUpdate, db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude={"updated_by"}, exclude_unset=True)
    try:
        return execution_agent.update_entity(db, "decision", entity_id, fields, updated_by=payload.updated_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=error_detail(exc)) from exc


@router.delete("/decisions/{entity_id}", status_code=204)
def delete_decision(entity_id: str, db: Session = Depends(get_db)):
    try:
        execution_agent.delete_entity(db, "decision", entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=error_detail(exc)) from exc


@router.post("/orchestrate/draft", response_model=DraftResponse)
def orchestrate_draft(payload: DraftRequest, db: Session = Depends(get_db)):
    try:
        result = orchestrator_service.run_draft(
            db,
            task_type=payload.task_type,
            user_prompt=payload.user_prompt,
            doc_type_filter=payload.doc_type_filter,
            required_sections=payload.required_sections,
            language=payload.language,
        )
    except openai.RateLimitError as exc:
        raise HTTPException(
            status_code=429, detail={"error_code": "ai_quota_exceeded", "params": {}}
        ) from exc
    except openai.APIStatusError as exc:
        raise HTTPException(status_code=502, detail={"error_code": "ai_provider_error", "params": {}}) from exc
    return DraftResponse(
        task_type=result["task_type"],
        draft=result.get("draft", ""),
        references=result.get("references", []),
        confidence=result.get("confidence", 0.0),
        validation_issues=result.get("validation_issues", []),
        retrieved_docs=result.get("retrieved_docs", []),
        trace=result.get("trace", []),
    )


@router.post("/orchestrate/chat")
def orchestrate_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    def event_stream():
        for event in chat_agent.run_chat(db, [m.model_dump() for m in payload.messages], language=payload.language):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/orchestrate/execute", response_model=ExecuteResponse)
def orchestrate_execute(payload: ExecuteRequest, db: Session = Depends(get_db)):
    try:
        result = orchestrator_service.run_execute(
            db,
            entity_type=payload.entity_type,
            title=payload.title,
            content=payload.content,
            references=payload.references,
            created_by=payload.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_detail(exc)) from exc
    return ExecuteResponse(**result)


@router.post("/orchestrate/publish", response_model=PublishResponse)
def orchestrate_publish(payload: PublishRequest, db: Session = Depends(get_db)):
    try:
        result = orchestrator_service.run_publish(
            db,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            requested_by=payload.requested_by,
            title=payload.title,
        )
    except ValueError as exc:
        status_code = 409 if isinstance(exc, DomainError) and exc.code == "publish_not_approved" else 404
        raise HTTPException(status_code=status_code, detail=error_detail(exc)) from exc
    return PublishResponse(**result)


@router.get("/documents/{entity_type}/{entity_id}/versions", response_model=VersionsResponse)
def document_versions(entity_type: str, entity_id: str, db: Session = Depends(get_db)):
    try:
        versions = orchestrator_service.list_versions(db, entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_detail(exc)) from exc
    return VersionsResponse(
        entity_type=entity_type,
        entity_id=entity_id,
        versions=[
            VersionOut(
                version=v.version,
                title=v.title,
                content=v.content,
                status=v.status,
                created_by=v.created_by,
                created_at=v.created_at.isoformat(),
            )
            for v in versions
        ],
    )


@router.get("/documents/search", response_model=SearchResponse)
def documents_search(q: str, doc_type: str | None = None, top_k: int = 5, db: Session = Depends(get_db)):
    candidates = search_documents(db, query=q, top_k=max(top_k * 3, 15), doc_type=doc_type)
    hits = build_context(rerank(q, candidates, top_k=top_k))
    return SearchResponse(query=q, results=[h.__dict__ for h in hits])


@router.post("/documents/ingest", response_model=IngestResponse)
def documents_ingest(payload: IngestRequest, db: Session = Depends(get_db)):
    document, chunk_count = ingest_text(db, payload.title, payload.doc_type, payload.source, payload.content)
    return IngestResponse(document_id=str(document.id), chunks_created=chunk_count)


@router.post("/documents/upload", response_model=IngestResponse)
async def documents_upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    doc_type: str = Form("general"),
    db: Session = Depends(get_db),
):
    """Upload/OCR stage of the Knowledge Layer pipeline: Upload -> OCR ->
    Cleaning -> Chunking -> Metadata Extraction -> Embeddings -> Vector DB."""
    content_bytes = await file.read()

    try:
        extracted_text = ocr(file.filename, content_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_detail(exc)) from exc

    if not extracted_text.strip():
        raise HTTPException(status_code=422, detail={"error_code": "no_extractable_text", "params": {}})

    store_document(file.filename, content_bytes)

    document, chunk_count = ingest_text(
        db, title or file.filename, doc_type, f"upload:{file.filename}", extracted_text
    )
    return IngestResponse(document_id=str(document.id), chunks_created=chunk_count)
