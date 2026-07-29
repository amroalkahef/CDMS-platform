"""Retrieval Agent.

Purpose: retrieve relevant information. Never generates content.

Pipeline: Hybrid Search (wide candidate pool) -> Re-ranking -> Context
Builder (dedupe + budget) -> hand off to the Authoring Agent.
"""

import time

from sqlalchemy.orm import Session

from app.orchestrator.context_builder import build_context
from app.orchestrator.state import AgentState
from app.tools.audit import log_audit
from app.tools.rerank import rerank
from app.tools.search import search_documents

TOP_K = 5
CANDIDATE_POOL = 15


def run(state: AgentState, db: Session) -> AgentState:
    start = time.perf_counter()
    query = state["user_prompt"]

    candidates = search_documents(
        db,
        query=query,
        top_k=CANDIDATE_POOL,
        doc_type=state.get("doc_type_filter"),
    )
    reranked = rerank(query, candidates, top_k=TOP_K)
    hits = build_context(reranked)

    state["retrieved_docs"] = [
        {
            "document_id": h.document_id,
            "title": h.title,
            "doc_type": h.doc_type,
            "chunk_content": h.chunk_content,
            "similarity": h.similarity,
        }
        for h in hits
    ]

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="retrieval_agent",
        action="search_documents",
        prompt=state["user_prompt"],
        duration_ms=duration_ms,
        final_response=f"{len(candidates)} candidates -> {len(reranked)} reranked -> {len(hits)} in final context",
    )
    state.setdefault("trace", []).append(
        {
            "agent": "retrieval_agent",
            "duration_ms": duration_ms,
            "candidates": len(candidates),
            "reranked": len(reranked),
            "final_context": len(hits),
        }
    )
    return state
