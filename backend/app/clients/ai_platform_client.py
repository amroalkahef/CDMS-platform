"""HTTP client for the (separate) AI Platform service. The web app never
calls the AI Platform directly — every AI request goes through this
Backend, which enforces permissions before delegating."""

from typing import AsyncIterator

import httpx

from app.config import get_settings


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(base_url=settings.ai_platform_base_url, timeout=60.0)


async def chat_stream(payload: dict) -> AsyncIterator[bytes]:
    """Async streaming relay for /orchestrate/chat — unlike every other
    function in this file, this one opens its client inside the generator
    and keeps it alive for the duration of the stream (a plain `with
    _client() as client:` closes as soon as the function returns, before the
    body is consumed). Async (not the rest of the file's sync httpx.Client)
    so the ASGI server can observe a client disconnect promptly instead of
    only via iterate_in_threadpool."""
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.ai_platform_base_url, timeout=120.0) as client:
        async with client.stream("POST", "/orchestrate/chat", json=payload) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk


def draft(payload: dict) -> dict:
    with _client() as client:
        response = client.post("/orchestrate/draft", json=payload)
        response.raise_for_status()
        return response.json()


def execute(payload: dict) -> dict:
    with _client() as client:
        response = client.post("/orchestrate/execute", json=payload)
        response.raise_for_status()
        return response.json()


def publish(payload: dict) -> dict:
    with _client() as client:
        response = client.post("/orchestrate/publish", json=payload)
        response.raise_for_status()
        return response.json()


def search(query: str, doc_type: str | None = None, top_k: int = 5) -> dict:
    with _client() as client:
        params = {"q": query, "top_k": top_k}
        if doc_type:
            params["doc_type"] = doc_type
        response = client.get("/documents/search", params=params)
        response.raise_for_status()
        return response.json()


def ingest(payload: dict) -> dict:
    with _client() as client:
        response = client.post("/documents/ingest", json=payload)
        response.raise_for_status()
        return response.json()


def versions(entity_type: str, entity_id: str) -> dict:
    with _client() as client:
        response = client.get(f"/documents/{entity_type}/{entity_id}/versions")
        response.raise_for_status()
        return response.json()


def upload(filename: str, content: bytes, title: str | None, doc_type: str) -> dict:
    with _client() as client:
        files = {"file": (filename, content)}
        data = {"doc_type": doc_type}
        if title:
            data["title"] = title
        response = client.post("/documents/upload", files=files, data=data)
        response.raise_for_status()
        return response.json()


def get_constants() -> dict:
    with _client() as client:
        response = client.get("/constants")
        response.raise_for_status()
        return response.json()


def get_stats() -> dict:
    with _client() as client:
        response = client.get("/stats")
        response.raise_for_status()
        return response.json()


def similarity_check(payload: dict) -> dict:
    with _client() as client:
        response = client.post("/similarity-check", json=payload)
        response.raise_for_status()
        return response.json()


def list_entities(entity_type: str, params: dict) -> list:
    with _client() as client:
        response = client.get(f"/{entity_type}s", params={k: v for k, v in params.items() if v is not None})
        response.raise_for_status()
        return response.json()


def create_entity(entity_type: str, payload: dict) -> dict:
    with _client() as client:
        response = client.post(f"/{entity_type}s", json=payload)
        response.raise_for_status()
        return response.json()


def get_entity(entity_type: str, entity_id: str) -> dict:
    with _client() as client:
        response = client.get(f"/{entity_type}s/{entity_id}")
        response.raise_for_status()
        return response.json()


def update_entity(entity_type: str, entity_id: str, payload: dict) -> dict:
    with _client() as client:
        response = client.patch(f"/{entity_type}s/{entity_id}", json=payload)
        response.raise_for_status()
        return response.json()


def delete_entity(entity_type: str, entity_id: str) -> None:
    with _client() as client:
        response = client.delete(f"/{entity_type}s/{entity_id}")
        response.raise_for_status()
