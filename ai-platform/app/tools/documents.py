"""StoreDocument() / OCR() / GeneratePDF() shared tools.

OCR runs fully locally (no cloud provider / API key required):
- .txt          -> decoded directly
- .pdf          -> text layer extracted via pypdf; pages with no extractable
                   text (scanned PDFs) fall back to rendering + Tesseract OCR
- .png/.jpg/... -> Tesseract OCR directly

StoreDocument persists to local disk to stand in for Object Storage
(S3 / Azure Blob) until a real object store is wired in.
"""

import io
import os
import uuid

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
from pypdf import PdfReader

from app.config import get_settings
from app.errors import DomainError

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}

# Combined language pack (Dockerfile installs both tesseract-ocr-eng and
# -ara) so scanned English and Arabic documents both OCR correctly without
# knowing the document's language ahead of time; Tesseract's LSTM engine
# handles a mixed-language pass reasonably well.
OCR_LANGUAGES = "eng+ara"


def store_document(filename: str, content: bytes) -> str:
    settings = get_settings()
    os.makedirs(settings.documents_storage_path, exist_ok=True)
    safe_name = f"{uuid.uuid4()}-{filename}"
    path = os.path.join(settings.documents_storage_path, safe_name)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _ocr_image_bytes(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang=OCR_LANGUAGES)


def _ocr_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text: list[str] = []
    needs_ocr_pages: list[int] = []

    for index, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            pages_text.append(text)
        else:
            pages_text.append("")
            needs_ocr_pages.append(index)

    if needs_ocr_pages:
        images = convert_from_bytes(file_bytes)
        for index in needs_ocr_pages:
            if index < len(images):
                buf = io.BytesIO()
                images[index].save(buf, format="PNG")
                pages_text[index] = pytesseract.image_to_string(images[index], lang=OCR_LANGUAGES)

    return "\n\n".join(t for t in pages_text if t)


def ocr(filename: str, file_bytes: bytes) -> str:
    """Extract text from an uploaded file. Raises ValueError for unsupported
    file types rather than silently returning nothing."""
    ext = os.path.splitext(filename.lower())[1]

    if ext == ".txt":
        return file_bytes.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        return _ocr_pdf(file_bytes)
    if ext in IMAGE_EXTENSIONS:
        return _ocr_image_bytes(file_bytes)

    raise DomainError("unsupported_file_type", ext=ext, allowed=", ".join([".txt", ".pdf", *sorted(IMAGE_EXTENSIONS)]))


def generate_pdf(title: str, content: str) -> bytes:
    """Stub: real implementation should render HTML/markdown to PDF."""
    raise NotImplementedError("PDF generation is not wired up yet")
