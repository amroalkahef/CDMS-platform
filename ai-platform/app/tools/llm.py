"""Thin wrapper around the OpenAI client so every agent shares one client
instance and one place to swap providers later. Any OpenAI-compatible
endpoint works here (Azure OpenAI, Gemini's OpenAI-compat layer, Groq, etc) —
just set LLM_BASE_URL alongside LLM_API_KEY."""

from functools import lru_cache

from openai import OpenAI

from app.config import get_settings


@lru_cache
def get_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url or None)


@lru_cache
def get_embedding_client() -> OpenAI:
    """Separate client for embeddings: some chat providers (e.g. Groq) don't
    serve an embeddings endpoint, so this falls back to the main LLM
    credentials only when no embedding-specific ones are set."""
    settings = get_settings()
    return OpenAI(
        api_key=settings.embedding_api_key or settings.llm_api_key,
        base_url=settings.embedding_base_url or settings.llm_base_url or None,
    )
