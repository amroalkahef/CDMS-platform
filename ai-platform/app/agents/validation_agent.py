"""Validation Agent.

Purpose: validate AI output before it reaches the user. Never edits — it
only reports issues (formatting, missing sections, hallucinations, citation
accuracy, duplicate documents, etc).
"""

import json
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import DomainError
from app.models import Circular, Decision, EntityChunk
from app.orchestrator.state import AgentState
from app.tools.audit import log_audit
from app.tools.embeddings import chunk_text, generate_embeddings
from app.tools.llm import get_client

_ENTITY_MODELS = {"circular": Circular, "decision": Decision}
SIMILARITY_DUPLICATE_THRESHOLD = 0.85
LEXICAL_TITLE_THRESHOLD = 0.25

SYSTEM_PROMPT = """You are the Validation Agent of an enterprise AI platform. \
You review a drafted document against the reference context it was supposed \
to be grounded in. You NEVER rewrite or fix the draft — you only report issues.

Return a JSON object: {"issues": [{"severity": "error"|"warning"|"info", \
"category": "hallucination"|"citation"|"writing_style"|"policy_compliance", \
"message": "..."}]}. If there are no issues, return {"issues": []}.

Flag:
- Claims in the draft not supported by the reference context (hallucinations)
- Missing or fabricated citations
- Inappropriate or informal tone for an official administrative document

Write each "message" in the same language as the draft being reviewed (e.g. \
Arabic issues for an Arabic draft), not necessarily the language of this prompt.
"""

DUPLICATE_VERIFICATION_PROMPT = """You are the Validation Agent's duplicate-detection \
reviewer. You are given a NEW draft (title + content) and a list of EXISTING candidate \
records retrieved because they are textually or semantically similar. The candidates \
were surfaced by an embedding/trigram search, which often over-triggers on shared \
boilerplate, formatting, or generic administrative phrasing even when the actual subject \
matter is unrelated — ignore that kind of surface overlap. For EACH candidate, classify \
its relationship to the new draft as exactly one of:

- "duplicate": substantively the same content/decision — differs only in wording,
  formatting, or minor detail. Publishing both would be redundant.
- "related": same topic or overlapping subject matter, but materially different
  content, scope, or decision.
- "different": not actually similar — retrieval picked it up by coincidence
  (shared boilerplate, common words, etc).

Also score how similar the two documents actually are in SUBSTANCE (subject, decision, \
entities involved, scope) on a 0-100 scale, where 0 means unrelated content and 100 means \
identical content. Base this purely on meaning, not on shared template language. A \
"different" verdict should almost always carry a low score (well under 40); "duplicate" \
should carry a high score.

Return JSON: {"verdicts": [{"id": "<candidate id>", "verdict": "duplicate"|"related"|"different", \
"similarity_score": <integer 0-100>, "explanation": "one short sentence, specific to this candidate"}]}. \
Include every candidate exactly once, using the exact id given.

Write each "explanation" in the same language as the new draft (e.g. Arabic \
explanations for an Arabic draft), not necessarily the language of this prompt.
"""


def _rule_based_checks(state: AgentState) -> list[dict]:
    issues: list[dict] = []
    draft = state.get("draft", "")

    if not draft.strip():
        issues.append({"severity": "error", "category": "missing_content", "message": "Draft is empty."})
        return issues

    for section in state.get("required_sections", []):
        if section.lower() not in draft.lower():
            issues.append(
                {
                    "severity": "warning",
                    "category": "missing_section",
                    "message": f"Required section '{section}' was not found in the draft.",
                }
            )

    if not state.get("retrieved_docs"):
        issues.append(
            {
                "severity": "warning",
                "category": "citation",
                "message": "No reference documents were retrieved; draft may be ungrounded.",
            }
        )

    return issues


def _llm_checks(state: AgentState) -> list[dict]:
    docs = state.get("retrieved_docs", [])
    if not docs or not state.get("draft"):
        return []

    settings = get_settings()
    client = get_client()
    context_block = "\n\n".join(f"[{d['title']}]\n{d['chunk_content']}" for d in docs)

    completion = client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Reference context:\n{context_block}\n\nDraft:\n{state['draft']}",
            },
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        payload = json.loads(completion.choices[0].message.content or "{}")
        return payload.get("issues", [])
    except json.JSONDecodeError:
        return [
            {
                "severity": "warning",
                "category": "validation_error",
                "message": "Validation Agent returned a non-JSON response and was skipped.",
            }
        ]


def _retrieve_chunk_candidates(
    db: Session, entity_type: str, chunks: list[str], exclude_id: str | None, top_k: int
) -> dict[str, dict]:
    """Stage 1a (semantic retrieval): embed each query chunk and search the
    EntityChunk index, aggregating to entity-level by keeping each entity's
    single best-matching chunk. This is finer-grained than embedding the
    whole draft once, so a duplicated paragraph inside an otherwise-new
    document still surfaces."""
    try:
        embeddings = generate_embeddings(chunks)
    except Exception:
        # Debounced-as-you-type check — degrade gracefully rather than
        # surfacing an OpenAI outage/quota error in the form UI.
        return {}

    candidates: dict[str, dict] = {}
    for chunk_embedding in embeddings:
        stmt = (
            select(EntityChunk, EntityChunk.embedding.cosine_distance(chunk_embedding).label("distance"))
            .where(EntityChunk.entity_type == entity_type)
            .order_by("distance")
            .limit(top_k * 3)
        )
        for chunk_row, distance in db.execute(stmt).all():
            if exclude_id and str(chunk_row.entity_id) == str(exclude_id):
                continue
            similarity = max(0.0, 1.0 - float(distance))
            key = str(chunk_row.entity_id)
            if key not in candidates or similarity > candidates[key]["similarity"]:
                candidates[key] = {"similarity": similarity, "snippet": chunk_row.content, "source": "semantic"}
    return candidates


def _retrieve_lexical_candidates(
    db: Session, entity_type: str, title: str, exclude_id: str | None, top_k: int
) -> dict[str, dict]:
    """Stage 1b (lexical retrieval): trigram title similarity via pg_trgm.
    Catches near-identical titles (typos, reordered words) independently of
    embeddings, and keeps duplicate detection working even when OpenAI is
    unavailable."""
    if not title.strip():
        return {}

    model = _ENTITY_MODELS[entity_type]
    title_sim = func.similarity(model.title, title)
    stmt = (
        select(model, title_sim.label("title_sim"))
        .where(title_sim > LEXICAL_TITLE_THRESHOLD)
        .order_by(title_sim.desc())
        .limit(top_k)
    )
    candidates: dict[str, dict] = {}
    for entity, title_sim in db.execute(stmt).all():
        if exclude_id and str(entity.id) == str(exclude_id):
            continue
        candidates[str(entity.id)] = {"similarity": float(title_sim), "snippet": entity.title, "source": "lexical"}
    return candidates


def _verify_candidates_with_llm(title: str, content: str, candidates: list[dict]) -> dict[str, dict]:
    """Stage 2 (generation/verification): a raw similarity score can't say
    *why* two records are alike, and pure cosine similarity over-triggers on
    generic topics. This asks the model to actually compare the new draft
    against each candidate and return a reasoned verdict — the part that
    makes this a real RAG pipeline rather than a nearest-neighbor lookup."""
    if not candidates:
        return {}

    settings = get_settings()
    client = get_client()
    candidates_block = "\n\n".join(f"[id={c['id']}] {c['title']}\n{c['snippet']}" for c in candidates)

    try:
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": DUPLICATE_VERIFICATION_PROMPT},
                {
                    "role": "user",
                    "content": f"New draft:\nTitle: {title}\n{content[:2000]}\n\nCandidates:\n{candidates_block}",
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
        return {v["id"]: v for v in payload.get("verdicts", []) if "id" in v}
    except Exception:
        return {}


def check_similarity(
    db: Session, entity_type: str, title: str, content: str, exclude_id: str | None = None, top_k: int = 5
) -> list[dict]:
    """Duplicate-detection RAG pipeline (PRD: Validation Agent -> 'Duplicate
    Documents'): chunk-level semantic retrieval + trigram lexical retrieval,
    merged and handed to the LLM for a verified duplicate/related/different
    verdict with an explanation — not just a bare cosine-similarity score."""
    if entity_type not in _ENTITY_MODELS:
        raise DomainError("unknown_entity_type", entity_type=entity_type, allowed=", ".join(_ENTITY_MODELS))

    text_input = f"{title}\n{content}".strip()
    if not text_input:
        return []

    chunks = chunk_text(text_input) or [text_input]

    semantic = _retrieve_chunk_candidates(db, entity_type, chunks, exclude_id, top_k)
    lexical = _retrieve_lexical_candidates(db, entity_type, title, exclude_id, top_k)

    merged: dict[str, dict] = dict(semantic)
    for entity_id, info in lexical.items():
        if entity_id not in merged or info["similarity"] > merged[entity_id]["similarity"]:
            merged[entity_id] = info

    if not merged:
        return []

    top_ids = sorted(merged, key=lambda k: merged[k]["similarity"], reverse=True)[:top_k]

    model = _ENTITY_MODELS[entity_type]
    entities = {str(e.id): e for e in db.execute(select(model).where(model.id.in_(top_ids))).scalars().all()}
    top_ids = [eid for eid in top_ids if eid in entities]  # entity may have been deleted since indexing

    verdicts = _verify_candidates_with_llm(
        title, content, [{"id": eid, "title": entities[eid].title, "snippet": merged[eid]["snippet"][:500]} for eid in top_ids]
    )

    results = []
    for entity_id in top_ids:
        entity = entities[entity_id]
        retrieval_similarity = round(merged[entity_id]["similarity"], 4)
        verdict_info = verdicts.get(entity_id)
        if verdict_info:
            verdict = verdict_info.get("verdict", "unknown")
            explanation = verdict_info.get("explanation")
            is_duplicate = verdict == "duplicate"
            # Prefer the LLM's content-grounded score over raw retrieval
            # similarity, which reflects surface/embedding closeness (shared
            # boilerplate, phrasing) rather than whether the documents are
            # actually about the same thing.
            llm_score = verdict_info.get("similarity_score")
            if isinstance(llm_score, (int, float)):
                similarity = round(max(0.0, min(100.0, llm_score)) / 100, 4)
            else:
                similarity = retrieval_similarity
        else:
            verdict = "unknown"
            explanation = None
            similarity = retrieval_similarity
            is_duplicate = similarity >= SIMILARITY_DUPLICATE_THRESHOLD

        results.append(
            {
                "id": entity_id,
                "title": entity.title,
                "department": entity.department,
                "status": entity.status,
                "similarity": similarity,
                "verdict": verdict,
                "explanation": explanation,
                "is_likely_duplicate": is_duplicate,
            }
        )
    return results


def run(state: AgentState, db: Session) -> AgentState:
    start = time.perf_counter()

    issues = _rule_based_checks(state) + _llm_checks(state)
    state["validation_issues"] = issues

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="validation_agent",
        action="validate_draft",
        duration_ms=duration_ms,
        final_response=f"{len(issues)} issue(s) found",
    )
    state.setdefault("trace", []).append(
        {"agent": "validation_agent", "duration_ms": duration_ms, "issues": len(issues)}
    )
    return state
