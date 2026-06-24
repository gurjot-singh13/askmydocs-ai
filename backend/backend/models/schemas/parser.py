import uuid

from pydantic import BaseModel


class PageText(BaseModel):
    """Text extracted from a single PDF page."""
    page_number: int   # 1-indexed
    text: str
    char_count: int


class ExtractionResult(BaseModel):
    """
    Result of extracting text from a document.

    This is an internal/diagnostic shape for Phase 2A — it is returned by the
    parser service and exposed via a debug endpoint. Later phases (chunking,
    embedding) will consume `pages` directly rather than this response model.
    """
    document_id: uuid.UUID
    file_type: str
    page_count: int
    total_char_count: int
    pages: list[PageText]
