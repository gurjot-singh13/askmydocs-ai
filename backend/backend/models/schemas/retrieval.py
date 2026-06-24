import uuid

from pydantic import BaseModel, ConfigDict


class SearchHit(BaseModel):
    """A single chunk returned by semantic search, ranked by similarity."""
    chunk_index: int
    text: str
    char_count: int
    similarity_score: float  # cosine similarity in [-1, 1]; higher is more relevant


class SearchResult(BaseModel):
    """Complete result of a semantic search over a document's chunks."""
    model_config = ConfigDict(protected_namespaces=())

    document_id: uuid.UUID
    query: str
    model_name: str
    top_k: int              # number of results requested
    total_chunks: int       # total chunks in the document (search space size)
    hits: list[SearchHit]   # ranked best-first, len <= top_k
