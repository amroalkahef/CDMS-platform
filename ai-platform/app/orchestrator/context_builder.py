"""Context Builder stage of the Knowledge Layer pipeline (Hybrid Search ->
Re-ranking -> Context Builder -> AI Agent). Deduplicates near-identical
chunks and enforces a character budget so the Authoring Agent gets a clean,
bounded context window instead of raw re-ranker output."""

from app.tools.search import SearchHit

DEFAULT_MAX_CHARS = 6000


def build_context(hits: list[SearchHit], max_chars: int = DEFAULT_MAX_CHARS) -> list[SearchHit]:
    deduped: list[SearchHit] = []
    seen_content: set[str] = set()

    for hit in hits:
        fingerprint = " ".join(hit.chunk_content.split())[:200]
        if fingerprint in seen_content:
            continue
        seen_content.add(fingerprint)
        deduped.append(hit)

    budgeted: list[SearchHit] = []
    used_chars = 0
    for hit in deduped:
        chunk_len = len(hit.chunk_content)
        if used_chars + chunk_len > max_chars and budgeted:
            break
        budgeted.append(hit)
        used_chars += chunk_len

    return budgeted
