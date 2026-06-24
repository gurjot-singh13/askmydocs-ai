import logging
import threading
import uuid

import chromadb
from chromadb.api.models.Collection import Collection

from config import settings
from models.schemas.chunk import ChunkingResult
from models.schemas.retrieval import SearchHit, SearchResult
from models.schemas.vector_store import IndexResult

logger = logging.getLogger(__name__)

# ── Collection configuration ─────────────────────────────────────────────────
COLLECTION_NAME = "document_chunks"

# Cosine space is set explicitly so distances are directly comparable to the
# in-memory cosine similarity computed in retrieval_service (Phase 5A):
#   similarity = 1 - cosine_distance
# Without this, Chroma defaults to squared-L2 distance, which is on a
# different numerical scale and would silently break score comparability.
_COLLECTION_METADATA = {"hnsw:space": "cosine"}

# ── Lazy, thread-safe singleton client ───────────────────────────────────────
# PersistentClient opens/creates the on-disk SQLite + HNSW index at
# settings.CHROMA_PERSIST_DIR. One client per process, reused across requests.
_client: chromadb.ClientAPI | None = None
_client_lock = threading.Lock()


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-checked locking
                logger.info(
                    "Opening ChromaDB persistent client at %s",
                    settings.CHROMA_PERSIST_DIR,
                )
                _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def _get_collection() -> Collection:
    """Return the shared chunk collection, creating it on first use."""
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata=_COLLECTION_METADATA,
    )


def _chunk_id(document_id: uuid.UUID, chunk_index: int) -> str:
    """
    Deterministic Chroma point ID for a given document chunk.

    Using a deterministic ID (rather than a random UUID per chunk) makes
    `upsert` idempotent — re-indexing the same document_id + chunk_index
    overwrites the existing vector instead of creating a duplicate.
    """
    return f"{document_id}:{chunk_index}"


# ── Public API ────────────────────────────────────────────────────────────────

def index_document(
    chunking_result: ChunkingResult,
    chunk_vectors: list[list[float]],
    model_name: str,
) -> IndexResult:
    """
    Persist a document's chunks and their embeddings into ChromaDB.

    If the document was previously indexed, its existing vectors are deleted
    first so re-indexing with different chunk_size/overlap settings doesn't
    leave orphaned chunks from the old configuration behind.

    Args:
        chunking_result: Output of chunk_service.chunk_document().
        chunk_vectors:   Full embedding vectors, same order as
                         chunking_result.chunks (from embedding_service.embed_chunks()).
        model_name:      Name of the embedding model used — stored as metadata
                         so future queries can verify model compatibility.

    Returns:
        IndexResult summarising what was written.

    Raises:
        ValueError: if chunk_vectors is empty or its length doesn't match
                    the number of chunks.
    """
    chunks = chunking_result.chunks

    if not chunk_vectors:
        raise ValueError("chunk_vectors is empty — nothing to index.")
    if len(chunk_vectors) != len(chunks):
        raise ValueError(
            f"chunk_vectors length ({len(chunk_vectors)}) does not match "
            f"number of chunks ({len(chunks)})."
        )

    collection = _get_collection()
    document_id_str = str(chunking_result.document_id)

    # ── Remove any existing vectors for this document (re-index support) ─────
    existing = collection.get(where={"document_id": document_id_str})
    reindexed = len(existing["ids"]) > 0
    if reindexed:
        collection.delete(where={"document_id": document_id_str})
        logger.info(
            "Removed %d existing vectors for document_id=%s before re-indexing",
            len(existing["ids"]),
            document_id_str,
        )

    # ── Write new vectors ──────────────────────────────────────────────────────
    ids = [_chunk_id(chunking_result.document_id, c.chunk_index) for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "document_id": document_id_str,
            "chunk_index": c.chunk_index,
            "char_count": c.char_count,
        }
        for c in chunks
    ]

    collection.upsert(
        ids=ids,
        embeddings=chunk_vectors,
        documents=documents,
        metadatas=metadatas,
    )

    logger.info(
        "Indexed document_id=%s: %d chunks written to ChromaDB collection '%s'",
        document_id_str,
        len(chunks),
        COLLECTION_NAME,
    )

    return IndexResult(
        document_id=chunking_result.document_id,
        collection_name=COLLECTION_NAME,
        model_name=model_name,
        embedding_dimension=len(chunk_vectors[0]),
        chunks_indexed=len(chunks),
        chunk_size=chunking_result.chunk_size,
        overlap=chunking_result.overlap,
        reindexed=reindexed,
    )


def is_indexed(document_id: uuid.UUID) -> bool:
    """Return True if the given document has at least one vector stored."""
    collection = _get_collection()
    result = collection.get(where={"document_id": str(document_id)}, limit=1)
    return len(result["ids"]) > 0


def delete_document_vectors(document_id: uuid.UUID) -> int:
    """
    Delete all vectors for a document from ChromaDB.

    Returns the number of vectors deleted. Intended to be called from
    document_service.delete_document() so removing a document also cleans
    up its index entries — kept as a separate function here so that
    document_service does not need to import ChromaDB directly.
    """
    collection = _get_collection()
    existing = collection.get(where={"document_id": str(document_id)})
    count = len(existing["ids"])
    if count > 0:
        collection.delete(where={"document_id": str(document_id)})
        logger.info("Deleted %d vectors for document_id=%s", count, document_id)
    return count


def search_indexed(
    document_id: uuid.UUID,
    query: str,
    query_vector: list[float],
    top_k: int = 5,
) -> SearchResult:
    """
    Query ChromaDB for the most similar chunks to a pre-embedded query vector,
    scoped to a single document.

    This function does NOT compute the query embedding itself — the caller
    (the /search route) is responsible for embedding the query via
    embedding_service.embed_chunks(), keeping vector_store_service focused
    purely on persistence and retrieval, not embedding generation.

    Args:
        document_id:  Restrict the search to chunks belonging to this document.
        query:        Raw query string — included in the response for context.
        query_vector: Pre-computed embedding of `query`.
        top_k:        Maximum number of results to return.

    Returns:
        SearchResult with hits ranked best-first by cosine similarity.

    Raises:
        ValueError: if the document has no indexed vectors. The caller should
                    catch this and respond with a clear "not indexed yet" error.
    """
    collection = _get_collection()
    document_id_str = str(document_id)

    # total_chunks is needed for the response and to validate the index exists
    existing = collection.get(where={"document_id": document_id_str})
    total_chunks = len(existing["ids"])

    if total_chunks == 0:
        raise ValueError(
            f"Document {document_id} has not been indexed yet. "
            f"Call POST /api/documents/{document_id}/index first."
        )

    effective_k = min(top_k, total_chunks)

    result = collection.query(
        query_embeddings=[query_vector],
        n_results=effective_k,
        where={"document_id": document_id_str},
    )

    # Chroma returns nested lists (one outer list per query embedding); we
    # only ever send one query embedding, so we unwrap index [0] throughout.
    hit_ids = result["ids"][0]
    hit_documents = result["documents"][0]
    hit_distances = result["distances"][0]
    hit_metadatas = result["metadatas"][0]

    hits: list[SearchHit] = []
    for doc_text, distance, metadata in zip(hit_documents, hit_distances, hit_metadatas):
        # Collection uses cosine space (hnsw:space="cosine"), so:
        #   cosine_distance = 1 - cosine_similarity
        similarity = 1.0 - distance
        hits.append(
            SearchHit(
                chunk_index=metadata["chunk_index"],
                text=doc_text,
                char_count=metadata["char_count"],
                similarity_score=round(float(similarity), 6),
            )
        )

    logger.info(
        "ChromaDB search complete: document_id=%s, query=%r, top_k=%d/%d",
        document_id_str,
        query[:60],
        len(hits),
        total_chunks,
    )

    return SearchResult(
        document_id=document_id,
        query=query,
        model_name="BAAI/bge-small-en-v1.5",
        top_k=top_k,
        total_chunks=total_chunks,
        hits=hits,
    )
