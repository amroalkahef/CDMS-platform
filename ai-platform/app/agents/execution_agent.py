"""Execution Agent.

Purpose: perform actions inside the system. This is the ONLY agent allowed
to modify data — no other agent, and no LLM call anywhere else in the
platform, may write to the database directly.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import communication_agent
from app.errors import DomainError
from app.models import Circular, Decision, DocumentVersion, EntityChunk
from app.tools.audit import log_audit
from app.tools.communication import call_rest_api
from app.tools.embeddings import chunk_text, generate_embeddings

logger = logging.getLogger("ai-platform.execution_agent")

_ENTITY_MODELS = {"circular": Circular, "decision": Decision}

# decision_number/circular_number are deliberately excluded here — they're
# system-generated in _generate_number(), never accepted from the client, on
# both create and update.
_ENTITY_FIELDS = {
    "circular": {"title", "content", "department", "frequency", "publication_date", "status", "references"},
    "decision": {"title", "content", "department", "effective_date", "status", "references"},
}

_NUMBER_FIELD = {"circular": "circular_number", "decision": "decision_number"}
_NUMBER_PREFIX = {"circular": "CIRC", "decision": "DEC"}


def _model(entity_type: str):
    model = _ENTITY_MODELS.get(entity_type)
    if model is None:
        raise DomainError("unknown_entity_type", entity_type=entity_type, allowed=", ".join(_ENTITY_MODELS))
    return model


def _generate_number(db: Session, entity_type: str) -> str:
    """Next sequential reference number for the current year, e.g.
    'CIRC-2026-0001' / 'DEC-2026-0001'. Scans for the first unused sequence
    starting from the current per-year count so it self-heals past gaps left
    by deleted rows or races with concurrent creates."""
    model = _model(entity_type)
    prefix = _NUMBER_PREFIX[entity_type]
    column = getattr(model, _NUMBER_FIELD[entity_type])
    year = datetime.now(timezone.utc).year
    like_pattern = f"{prefix}-{year}-%"

    seq = db.query(model).filter(column.like(like_pattern)).count() + 1
    while True:
        candidate = f"{prefix}-{year}-{seq:04d}"
        if db.query(model).filter(column == candidate).first() is None:
            return candidate
        seq += 1


def _snapshot_version(db: Session, entity_type: str, entity) -> None:
    """Workflow Engine versioning: write an immutable snapshot every time an
    entity's status changes (create, update, publish, ...)."""
    db.add(
        DocumentVersion(
            entity_type=entity_type,
            entity_id=entity.id,
            version=entity.version,
            title=entity.title,
            content=entity.content,
            status=entity.status,
            created_by=entity.created_by,
        )
    )
    db.commit()


def _sync_entity_chunks(db: Session, entity_type: str, entity) -> None:
    """(Re)builds the chunk-level embedding index behind the Similarity
    Check RAG pipeline. Must never block create/update — if OpenAI is
    unavailable (no quota, network, ...) the entity still saves, just
    without a fresh similarity index until the next successful sync."""
    db.query(EntityChunk).filter(EntityChunk.entity_type == entity_type, EntityChunk.entity_id == entity.id).delete()

    chunks = chunk_text(f"{entity.title}\n\n{entity.content}")
    if not chunks:
        db.commit()
        return

    try:
        embeddings = generate_embeddings(chunks)
    except Exception:
        logger.warning("Failed to generate chunk embeddings; similarity index left stale", exc_info=True)
        db.commit()
        return

    for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(
            EntityChunk(
                entity_type=entity_type, entity_id=entity.id, chunk_index=index, content=chunk_content, embedding=embedding
            )
        )
    db.commit()


def _register_workflow(db: Session, entity_type: str, entity, created_by: str) -> str | None:
    try:
        response = call_rest_api(
            "POST",
            "/api/workflows",
            json={
                "entity_type": entity_type,
                "entity_id": str(entity.id),
                "title": entity.title,
                "requested_by": created_by,
            },
        )
        return response.json().get("id")
    except Exception as exc:  # backend may be briefly unavailable in dev
        log_audit(
            db,
            agent="execution_agent",
            action="register_workflow_failed",
            final_response=str(exc),
            error=True,
        )
        return None


def create_entity(db: Session, entity_type: str, fields: dict, created_by: str = "dev-user") -> dict:
    """Create a Circular/Decision. If the given status is 'pending_approval',
    a workflow is registered with the Backend and its approvers notified
    (PRD Step 11)."""
    start = time.perf_counter()
    model = _model(entity_type)

    allowed = _ENTITY_FIELDS[entity_type]
    payload = {k: v for k, v in fields.items() if k in allowed and v is not None}
    payload.setdefault("status", "draft")
    payload.setdefault("references", [])
    payload[_NUMBER_FIELD[entity_type]] = _generate_number(db, entity_type)

    entity = model(version=1, created_by=created_by, **payload)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    _snapshot_version(db, entity_type, entity)
    _sync_entity_chunks(db, entity_type, entity)

    workflow_id = None
    if entity.status == "pending_approval":
        workflow_id = _register_workflow(db, entity_type, entity, created_by)
        if workflow_id:
            communication_agent.notify_approval_requested(
                db, workflow_id=workflow_id, title=entity.title, entity_type=entity_type
            )

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="execution_agent",
        action=f"create_{entity_type}",
        duration_ms=duration_ms,
        tool_calls=[{"tool": "call_rest_api", "path": "/api/workflows"}] if workflow_id else [],
        final_response=f"{entity_type} {entity.id} created (status={entity.status})",
        user_id=created_by,
    )

    return _to_dict(entity_type, entity) | {"workflow_id": workflow_id}


# Backward-compatible alias used by the /orchestrate/execute lifecycle demo.
def create_and_submit(
    db: Session, entity_type: str, title: str, content: str, references: list[dict], created_by: str = "dev-user"
) -> dict:
    result = create_entity(
        db, entity_type, {"title": title, "content": content, "references": references, "status": "pending_approval"}, created_by
    )
    return {
        "entity_id": result["id"],
        "entity_type": entity_type,
        "status": result["status"],
        "workflow_id": result["workflow_id"],
    }


def update_entity(db: Session, entity_type: str, entity_id: str, fields: dict, updated_by: str = "dev-user") -> dict:
    start = time.perf_counter()
    model = _model(entity_type)
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainError("entity_not_found", entity_type=entity_type, entity_id=entity_id)

    allowed = _ENTITY_FIELDS[entity_type]
    content_changed = False
    was_pending = entity.status == "pending_approval"
    for key, value in fields.items():
        if key in allowed and value is not None:
            if key in ("title", "content") and getattr(entity, key) != value:
                content_changed = True
            setattr(entity, key, value)

    entity.version += 1
    db.commit()
    db.refresh(entity)
    _snapshot_version(db, entity_type, entity)
    if content_changed:
        _sync_entity_chunks(db, entity_type, entity)

    workflow_id = None
    if entity.status == "pending_approval" and not was_pending:
        workflow_id = _register_workflow(db, entity_type, entity, updated_by)
        if workflow_id:
            communication_agent.notify_approval_requested(
                db, workflow_id=workflow_id, title=entity.title, entity_type=entity_type
            )

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="execution_agent",
        action=f"update_{entity_type}",
        duration_ms=duration_ms,
        final_response=f"{entity_type} {entity.id} updated to v{entity.version} (status={entity.status})",
        user_id=updated_by,
    )

    return _to_dict(entity_type, entity) | {"workflow_id": workflow_id}


def delete_entity(db: Session, entity_type: str, entity_id: str, deleted_by: str = "dev-user") -> None:
    start = time.perf_counter()
    model = _model(entity_type)
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainError("entity_not_found", entity_type=entity_type, entity_id=entity_id)

    db.query(DocumentVersion).filter(
        DocumentVersion.entity_type == entity_type, DocumentVersion.entity_id == entity_id
    ).delete()
    db.query(EntityChunk).filter(EntityChunk.entity_type == entity_type, EntityChunk.entity_id == entity_id).delete()
    db.delete(entity)
    db.commit()

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="execution_agent",
        action=f"delete_{entity_type}",
        duration_ms=duration_ms,
        final_response=f"{entity_type} {entity_id} deleted",
        user_id=deleted_by,
    )


def get_entity(db: Session, entity_type: str, entity_id: str) -> dict:
    model = _model(entity_type)
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainError("entity_not_found", entity_type=entity_type, entity_id=entity_id)
    return _to_dict(entity_type, entity)


def list_entities(
    db: Session, entity_type: str, status: str | None = None, department: str | None = None, q: str | None = None
) -> list[dict]:
    model = _model(entity_type)
    stmt = select(model).order_by(model.created_at.desc())
    if status:
        stmt = stmt.where(model.status == status)
    if department:
        stmt = stmt.where(model.department == department)
    if q:
        stmt = stmt.where(model.title.ilike(f"%{q}%"))
    entities = db.execute(stmt).scalars().all()
    return [_to_dict(entity_type, e) for e in entities]


def search_entities(db: Session, entity_type: str, query: str, limit: int = 5) -> list[dict]:
    """Keyword lookup for the chat assistant's find_records tool — matches
    title always, plus decision_number for decisions. Kept separate from
    list_entities() (which backs the live Circulars/Decisions list pages) so
    this can't regress that filter's behavior."""
    model = _model(entity_type)
    stmt = select(model).where(model.title.ilike(f"%{query}%"))
    if entity_type == "decision":
        stmt = select(model).where(
            model.title.ilike(f"%{query}%") | model.decision_number.ilike(f"%{query}%")
        )
    stmt = stmt.order_by(model.created_at.desc()).limit(limit)
    entities = db.execute(stmt).scalars().all()
    return [_to_dict(entity_type, e) for e in entities]


def publish(db: Session, entity_type: str, entity_id: str) -> dict:
    """Mark an entity published/active — mirrors PRD Step 13 ('Execution
    Agent publishes'), invoked by the Backend once the Editor confirms
    publish on a record the Reviewer has approved."""
    start = time.perf_counter()

    model = _model(entity_type)
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainError("entity_not_found", entity_type=entity_type, entity_id=entity_id)
    if entity.status != "approved":
        raise DomainError("publish_not_approved", entity_type=entity_type, entity_id=entity_id, status=entity.status)

    entity.status = "active" if entity_type == "decision" else "published"
    entity.version += 1
    entity.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entity)
    _snapshot_version(db, entity_type, entity)

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="execution_agent",
        action=f"publish_{entity_type}",
        duration_ms=duration_ms,
        final_response=f"{entity_type} {entity_id} published (v{entity.version})",
    )

    return {"entity_id": str(entity.id), "entity_type": entity_type, "status": entity.status, "version": entity.version}


def list_versions(db: Session, entity_type: str, entity_id: str) -> list[DocumentVersion]:
    if entity_type not in _ENTITY_MODELS:
        raise DomainError("unknown_entity_type", entity_type=entity_type, allowed=", ".join(_ENTITY_MODELS))

    return list(
        db.query(DocumentVersion)
        .filter(DocumentVersion.entity_type == entity_type, DocumentVersion.entity_id == entity_id)
        .order_by(DocumentVersion.version.asc())
        .all()
    )


def _to_dict(entity_type: str, entity) -> dict:
    base = {
        "id": str(entity.id),
        "entity_type": entity_type,
        "title": entity.title,
        "content": entity.content,
        "department": entity.department,
        "status": entity.status,
        "version": entity.version,
        "created_by": entity.created_by,
        "references": entity.references,
        "created_at": entity.created_at.isoformat(),
        "published_at": entity.published_at.isoformat() if entity.published_at else None,
    }
    if entity_type == "circular":
        base["circular_number"] = entity.circular_number
        base["frequency"] = entity.frequency
        base["publication_date"] = entity.publication_date.isoformat() if entity.publication_date else None
    else:
        base["decision_number"] = entity.decision_number
        base["effective_date"] = entity.effective_date.isoformat() if entity.effective_date else None
    return base
