"""Knowledge Layer ingestion pipeline: Cleaning -> Chunking -> Embeddings ->
Vector Database. (Upload/OCR are handled upstream — this scaffold accepts
raw text directly; wire file upload + OCR() in Phase 3.)
"""

import re

from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.tools.embeddings import chunk_text, generate_embeddings


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ingest_text(db: Session, title: str, doc_type: str, source: str, content: str) -> tuple[Document, int]:
    cleaned = _clean(content)

    document = Document(title=title, doc_type=doc_type, source=source, content=cleaned)
    db.add(document)
    db.flush()  # assign document.id without committing yet

    chunks = chunk_text(cleaned)
    if chunks:
        embeddings = generate_embeddings(chunks)
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=embedding,
                    meta={"doc_type": doc_type, "source": source},
                )
            )

    db.commit()
    db.refresh(document)
    return document, len(chunks)
