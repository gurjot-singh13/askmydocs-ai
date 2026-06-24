import uuid

from pydantic import BaseModel, ConfigDict


class IndexResult(BaseModel):
    """
    Result of indexing a document into ChromaDB.

    Returned by vector_store_service.index_document() and exposed via
    POST /api/documents/{document_id}/index.
    """
    model_config = ConfigDict(protected_namespaces=())

    document_id: uuid.UUID
    collection_name: str
    model_name: str
    embedding_dimension: int
    chunks_indexed: int
    chunk_size: int
    overlap: int
    reindexed: bool   # True if this document already had vectors that were replaced
