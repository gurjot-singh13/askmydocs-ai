import uuid
from pydantic import BaseModel


class Chunk(BaseModel):
    """
    A single text chunk produced by the chunking service.

    This is the unit consumed by the embedding pipeline in Phase 3B.
    It is intentionally free of document_id / user_id so the chunking
    service stays stateless — those fields are attached by the caller
    when persisting to PostgreSQL.
    """
    chunk_index: int       # 0-based position within the document
    text: str
    char_count: int


class ChunkingResult(BaseModel):
    """
    Complete output of chunking a single document.

    Returned by chunk_service.chunk_document() and exposed via the
    GET /api/documents/{document_id}/chunks endpoint.
    """
    document_id: uuid.UUID
    chunk_size: int         # configured window size used (characters)
    overlap: int            # configured overlap used (characters)
    total_chunks: int
    total_chars: int        # sum of all chunk char_counts (includes overlap)
    chunks: list[Chunk]
