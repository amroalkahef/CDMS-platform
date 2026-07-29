"""SearchDocuments() / SearchVectorDatabase() / SearchSQL() shared tools.

Implements a simple hybrid search: vector similarity (pgvector cosine
distance) combined with a SQL keyword/metadata filter, matching the
Retrieval Agent's responsibilities in the PRD (Semantic, Hybrid, Metadata,
SQL, Vector search).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Circular, Decision, Document, DocumentChunk, EntityChunk
from app.tools.embeddings import generate_embedding


@dataclass
class SearchHit:
    document_id: str
    title: str
    doc_type: str
    chunk_content: str
    similarity: float
    metadata: dict = field(default_factory=dict)


@dataclass
class EntityChunkHit:
    entity_type: str
    entity_id: str
    title: str
    department: str
    status: str
    chunk_content: str
    similarity: float


_ENTITY_MODELS = {"circular": Circular, "decision": Decision}


def search_entity_chunks(
    db: Session, query: str, entity_type: str | None = None, top_k: int = 5
) -> list[EntityChunkHit]:
    """Semantic search over EntityChunk (Circular/Decision content), the same
    embedding index the Similarity Check pipeline uses — reused here so chat
    can find records by meaning, not just exact title/number matches."""
    query_embedding = generate_embedding(query)
    hits: list[EntityChunkHit] = []

    entity_types = [entity_type] if entity_type else list(_ENTITY_MODELS)
    for etype in entity_types:
        model = _ENTITY_MODELS[etype]
        stmt = (
            select(
                EntityChunk,
                model,
                EntityChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(model, model.id == EntityChunk.entity_id)
            .where(EntityChunk.entity_type == etype)
            .order_by("distance")
            .limit(top_k)
        )
        for chunk, entity, distance in db.execute(stmt).all():
            similarity = max(0.0, 1.0 - float(distance))
            hits.append(
                EntityChunkHit(
                    entity_type=etype,
                    entity_id=str(entity.id),
                    title=entity.title,
                    department=entity.department,
                    status=entity.status,
                    chunk_content=chunk.content,
                    similarity=round(similarity, 4),
                )
            )

    hits.sort(key=lambda h: h.similarity, reverse=True)
    return hits[:top_k]


def search_vector_database(
    db: Session, query: str, top_k: int = 5, doc_type: str | None = None
) -> list[SearchHit]:
    """Semantic / vector search over document_chunks using cosine distance."""
    query_embedding = generate_embedding(query)

    stmt = (
        select(
            DocumentChunk,
            Document,
            DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by("distance")
        .limit(top_k)
    )
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)

    rows = db.execute(stmt).all()
    hits = []
    for chunk, document, distance in rows:
        similarity = max(0.0, 1.0 - float(distance))
        hits.append(
            SearchHit(
                document_id=str(document.id),
                title=document.title,
                doc_type=document.doc_type,
                chunk_content=chunk.content,
                similarity=round(similarity, 4),
                metadata=chunk.meta or {},
            )
        )
    return hits


def search_sql(db: Session, keyword: str, doc_type: str | None = None, limit: int = 10) -> list[Document]:
    """Plain keyword/metadata search over the documents table."""
    stmt = select(Document).where(Document.content.ilike(f"%{keyword}%")).limit(limit)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    return list(db.execute(stmt).scalars().all())


def search_documents(
    db: Session, query: str, top_k: int = 5, doc_type: str | None = None
) -> list[SearchHit]:
    """Hybrid search: vector search is primary; falls back to keyword search
    when the vector search returns nothing (e.g. empty corpus)."""
    hits = search_vector_database(db, query, top_k=top_k, doc_type=doc_type)
    if hits:
        return hits

    keyword_docs = search_sql(db, query, doc_type=doc_type, limit=top_k)
    return [
        SearchHit(
            document_id=str(doc.id),
            title=doc.title,
            doc_type=doc.doc_type,
            chunk_content=doc.content[:1200],
            similarity=0.0,
            metadata={"match": "keyword-fallback"},
        )
        for doc in keyword_docs
    ]
