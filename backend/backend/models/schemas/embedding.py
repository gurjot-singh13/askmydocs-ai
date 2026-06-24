import uuid

from pydantic import BaseModel, ConfigDict


class ChunkEmbedding(BaseModel):
    """
    Embedding result for a single chunk.

    `embedding_preview` holds only the first few dimensions of the vector —
    returning all 384 floats per chunk in an API response is unnecessary for
    a Phase 4A diagnostic endpoint and bloats the payload. The full vector is
    available in-process via embedding_service.embed_chunks() for callers
    that need it (e.g. the future vector-DB indexer in Phase 4B).
    """
    chunk_index: int
    char_count: int
    embedding_dimension: int
    embedding_preview: list[float]   # first N dimensions only, see PREVIEW_DIMS


class EmbeddingResult(BaseModel):
    """
    Complete output of embedding every chunk of a single document.

    Returned by embedding_service.embed_document() and exposed via the
    GET /api/documents/{document_id}/embeddings endpoint.
    """
    document_id: uuid.UUID
    model_config = ConfigDict(protected_namespaces=())
    model_name: str
    embedding_dimension: int
    total_chunks: int
    embeddings: list[ChunkEmbedding]
