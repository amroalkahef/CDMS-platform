"""Re-ranking stage of the Knowledge Layer pipeline (Hybrid Search -> Re-ranking
-> Context Builder). No cross-encoder model is bundled, so this uses the chat
model itself as a relevance judge over the candidate pool — cheap enough at
gpt-4o-mini scale for a handful of chunks, and provider-agnostic."""

import json

from app.config import get_settings
from app.tools.llm import get_client
from app.tools.search import SearchHit

SYSTEM_PROMPT = """You rank document chunks by relevance to a search query for \
retrieval-augmented generation. Return JSON: {"ranking": [chunk indices, most \
relevant first]}. Include every index exactly once. Judge relevance only —
ignore chunk length or writing quality."""


def rerank(query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
    if len(hits) <= 1:
        return hits[:top_k]

    settings = get_settings()
    client = get_client()

    candidates_block = "\n\n".join(f"[{i}] {h.title}\n{h.chunk_content[:800]}" for i, h in enumerate(hits))

    try:
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}\n\nChunks:\n{candidates_block}"},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
        order = [i for i in payload.get("ranking", []) if isinstance(i, int) and 0 <= i < len(hits)]
        seen = set(order)
        order += [i for i in range(len(hits)) if i not in seen]
        return [hits[i] for i in order[:top_k]]
    except (json.JSONDecodeError, KeyError, TypeError):
        # Re-ranking is a quality boost, not a hard dependency — fall back to
        # the original vector-similarity order rather than failing retrieval.
        return hits[:top_k]
