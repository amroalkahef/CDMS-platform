"""GenerateEmbeddings() shared tool."""

from app.config import get_settings
from app.tools.llm import get_embedding_client


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    settings = get_settings()
    client = get_embedding_client()
    response = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def generate_embedding(text: str) -> list[float]:
    return generate_embeddings([text])[0]


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Naive fixed-size chunker with overlap. Good enough for the scaffold;
    swap for a semantic/markdown-aware chunker in the real Knowledge Layer."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks
