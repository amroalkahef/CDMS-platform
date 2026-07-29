"""Everything the web app needs from the AI Platform goes through here —
this is where permission checks live (PRD 'AI Request Lifecycle' Step 3:
'Backend validates permissions'). Reading (search/lists/stats) is open to
any authenticated user; drafting/writing is editor-only; the reviewer's
approve/reject lives in workflows.py, not here."""

import json

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.auth import get_current_user, require_role
from app.clients import ai_platform_client
from app.errors import error_detail
from app.models import User
from app.schemas import (
    ChatProxyRequest,
    CircularCreateProxy,
    CircularUpdateProxy,
    DecisionCreateProxy,
    DecisionUpdateProxy,
    DraftProxyRequest,
    ExecuteProxyRequest,
    IngestProxyRequest,
    SimilarityCheckProxy,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _proxy(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except httpx.HTTPStatusError as exc:
        # ai-platform already returns {"detail": {"error_code": ..., "params":
        # ...}} for its own structured errors (see ai-platform/app/errors.py)
        # — forward that as-is instead of stuffing the raw response body
        # (English text, or the JSON itself) into `detail` as an opaque
        # string the frontend can't localize.
        try:
            detail = exc.response.json().get("detail") or error_detail("ai_provider_error")
        except ValueError:
            detail = error_detail("ai_provider_error")
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=error_detail("ai_platform_unreachable")) from exc


@router.post("/draft")
def draft(payload: DraftProxyRequest, _user: User = Depends(require_role("editor"))):
    return _proxy(ai_platform_client.draft, payload.model_dump())


@router.post("/chat")
async def chat(payload: ChatProxyRequest, _user: User = Depends(get_current_user)):
    """Streaming relay to /orchestrate/chat. Unlike _proxy() above, failures
    here can't become an HTTPException with a different status code —
    StreamingResponse sends the 200 header before the body iterator yields
    its first chunk, so by the time an upstream failure (ai-platform
    unreachable, etc.) is known, the response has already committed to 200.
    Surface it as an in-stream SSE error event instead, matching how
    chat_agent.py reports its own mid-stream failures."""

    async def relay():
        try:
            async for chunk in ai_platform_client.chat_stream(payload.model_dump()):
                yield chunk
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            yield f"data: {json.dumps({'type': 'error', 'error_code': 'ai_platform_unreachable'})}\n\n".encode()
            yield f"data: {json.dumps({'type': 'done'})}\n\n".encode()

    return StreamingResponse(relay(), media_type="text/event-stream")


@router.post("/execute")
def execute(payload: ExecuteProxyRequest, user: User = Depends(require_role("editor"))):
    body = payload.model_dump()
    body["created_by"] = user.name
    return _proxy(ai_platform_client.execute, body)


@router.get("/search")
def search(q: str, doc_type: str | None = None, top_k: int = 5, _user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.search, q, doc_type, top_k)


@router.post("/documents/ingest")
def ingest(payload: IngestProxyRequest, _user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.ingest, payload.model_dump())


@router.get("/documents/{entity_type}/{entity_id}/versions")
def versions(entity_type: str, entity_id: str, _user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.versions, entity_type, entity_id)


@router.post("/documents/upload")
async def upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    doc_type: str = Form("general"),
    _user: User = Depends(get_current_user),
):
    content = await file.read()
    return _proxy(ai_platform_client.upload, file.filename, content, title, doc_type)


@router.get("/constants")
def constants(_user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.get_constants)


@router.get("/stats")
def stats(_user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.get_stats)


@router.post("/similarity-check")
def similarity_check(payload: SimilarityCheckProxy, _user: User = Depends(require_role("editor"))):
    return _proxy(ai_platform_client.similarity_check, payload.model_dump(mode="json"))


def _publish(entity_type: str, entity_id: str, user: User):
    entity = _proxy(ai_platform_client.get_entity, entity_type, entity_id)
    if entity["status"] != "approved":
        raise HTTPException(
            status_code=409,
            detail=error_detail("publish_not_approved", entity_type=entity_type, entity_id=entity_id, status=entity["status"]),
        )
    return _proxy(
        ai_platform_client.publish,
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "requested_by": entity["created_by"],
            "title": entity["title"],
        },
    )


@router.get("/circulars")
def list_circulars(
    status: str | None = None, department: str | None = None, q: str | None = None, _user: User = Depends(get_current_user)
):
    return _proxy(ai_platform_client.list_entities, "circular", {"status": status, "department": department, "q": q})


@router.post("/circulars")
def create_circular(payload: CircularCreateProxy, user: User = Depends(require_role("editor"))):
    body = payload.model_dump(mode="json")
    body["created_by"] = user.name
    return _proxy(ai_platform_client.create_entity, "circular", body)


@router.get("/circulars/{entity_id}")
def get_circular(entity_id: str, _user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.get_entity, "circular", entity_id)


@router.patch("/circulars/{entity_id}")
def update_circular(entity_id: str, payload: CircularUpdateProxy, user: User = Depends(require_role("editor"))):
    body = payload.model_dump(mode="json", exclude_unset=True)
    body["updated_by"] = user.name
    return _proxy(ai_platform_client.update_entity, "circular", entity_id, body)


@router.delete("/circulars/{entity_id}", status_code=204)
def delete_circular(entity_id: str, _user: User = Depends(require_role("editor"))):
    return _proxy(ai_platform_client.delete_entity, "circular", entity_id)


@router.post("/circulars/{entity_id}/publish")
def publish_circular(entity_id: str, user: User = Depends(require_role("editor"))):
    return _publish("circular", entity_id, user)


@router.get("/decisions")
def list_decisions(
    status: str | None = None, department: str | None = None, q: str | None = None, _user: User = Depends(get_current_user)
):
    return _proxy(ai_platform_client.list_entities, "decision", {"status": status, "department": department, "q": q})


@router.post("/decisions")
def create_decision(payload: DecisionCreateProxy, user: User = Depends(require_role("editor"))):
    body = payload.model_dump(mode="json")
    body["created_by"] = user.name
    return _proxy(ai_platform_client.create_entity, "decision", body)


@router.get("/decisions/{entity_id}")
def get_decision(entity_id: str, _user: User = Depends(get_current_user)):
    return _proxy(ai_platform_client.get_entity, "decision", entity_id)


@router.patch("/decisions/{entity_id}")
def update_decision(entity_id: str, payload: DecisionUpdateProxy, user: User = Depends(require_role("editor"))):
    body = payload.model_dump(mode="json", exclude_unset=True)
    body["updated_by"] = user.name
    return _proxy(ai_platform_client.update_entity, "decision", entity_id, body)


@router.delete("/decisions/{entity_id}", status_code=204)
def delete_decision(entity_id: str, _user: User = Depends(require_role("editor"))):
    return _proxy(ai_platform_client.delete_entity, "decision", entity_id)


@router.post("/decisions/{entity_id}/publish")
def publish_decision(entity_id: str, user: User = Depends(require_role("editor"))):
    return _publish("decision", entity_id, user)
