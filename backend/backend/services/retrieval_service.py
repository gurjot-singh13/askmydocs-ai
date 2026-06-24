import logging

import numpy as np

from models.schemas.chunk import Chunk, ChunkingResult
from models.schemas.retrieval import SearchHit, SearchResult

logger = logging.getLogger(__name__)

# Imported at call time (not module level) to avoid a circular import and to
# keep the retrieval service testable with a mocked encoder.
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _cosine_similarity(query_vec: np.ndarray, chunk_matrix: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between one query vector and N chunk vectors.

    Both inputs are expected to be L2-normalised (which sentence-transformers
    guarantees when `normalize_embeddings=True`).  Under that condition,
    cosine similarity equals the dot product — no division by norms needed.

    Args:
        query_vec:    Shape (D,)   — the embedded query.
        chunk_matrix: Shape (N, D) — the stacked chunk embeddings.

    Returns:
        Shape (N,) float64 array of similarity scores in [-1, 1].
    """
    # matrix-vector dot product: (N, D) @ (D,) -> (N,)
    return chunk_matrix @ query_vec


def search(
    query: str,
    chunking_result: ChunkingResult,
    chunk_vectors: list[list[float]],
    top_k: int = 5,
) -> SearchResult:
    """
    Perform in-memory semantic search over a document's chunks.

    Steps:
        1. Embed the query using the BGE query-instruction prefix.
        2. Stack the pre-computed chunk vectors into a numpy matrix.
        3. Compute cosine similarity (dot product on L2-normalised vectors).
        4. Argsort descending, take top_k.
        5. Return ranked SearchHit list.

    Args:
        query:           Raw user query string.
        chunking_result: ChunkingResult from chunk_service — provides the
                         chunk text and metadata for each position.
        chunk_vectors:   Full 384-dim embeddings for every chunk, in the same
                         order as chunking_result.chunks.  These come from
                         embedding_service.embed_chunks().
        top_k:           Maximum number of results to return.  If the document
                         has fewer chunks than top_k, all chunks are returned.

    Returns:
        SearchResult with hits ranked best-first.

    Raises:
        ValueError: if chunk_vectors is empty or its length does not match
                    the number of chunks in chunking_result.
    """
    # ── Import here to avoid circular dependency at module load time ─────────
    from services.embedding_service import embed_chunks, MODEL_NAME

    chunks: list[Chunk] = chunking_result.chunks

    if not chunk_vectors:
        raise ValueError("chunk_vectors is empty — nothing to search over.")

    if len(chunk_vectors) != len(chunks):
        raise ValueError(
            f"chunk_vectors length ({len(chunk_vectors)}) does not match "
            f"number of chunks ({len(chunks)})."
        )

    # ── Step 1: embed the query with the BGE query-instruction prefix ─────────
    # BGE models are asymmetric: passages are embedded as-is (done in Phase 4A)
    # but queries should be prefixed with this instruction string to maximise
    # retrieval performance.  See: https://huggingface.co/BAAI/bge-small-en-v1.5
    prefixed_query = _QUERY_INSTRUCTION + query.strip()
    query_vectors = embed_chunks([prefixed_query])   # returns list[list[float]]
    query_vec = np.array(query_vectors[0], dtype=np.float64)

    # ── Step 2: stack chunk vectors into matrix ───────────────────────────────
    chunk_matrix = np.array(chunk_vectors, dtype=np.float64)  # shape (N, 384)

    # ── Step 3: cosine similarity ─────────────────────────────────────────────
    scores: np.ndarray = _cosine_similarity(query_vec, chunk_matrix)  # shape (N,)

    # ── Step 4: rank and select top_k ────────────────────────────────────────
    effective_k = min(top_k, len(chunks))
    # argsort ascending; take last `effective_k` reversed for descending order
    ranked_indices = np.argsort(scores)[::-1][:effective_k]

    # ── Step 5: build hits ────────────────────────────────────────────────────
    hits: list[SearchHit] = [
        SearchHit(
            chunk_index=chunks[i].chunk_index,
            text=chunks[i].text,
            char_count=chunks[i].char_count,
            similarity_score=float(round(float(scores[i]), 6)),
        )
        for i in ranked_indices
    ]

    logger.info(
        "Search complete: query=%r, document_id=%s, top_k=%d/%d, "
        "top_score=%.4f",
        query[:60],
        chunking_result.document_id,
        len(hits),
        len(chunks),
        hits[0].similarity_score if hits else 0.0,
    )

    return SearchResult(
        document_id=chunking_result.document_id,
        query=query,
        model_name=MODEL_NAME,
        top_k=top_k,
        total_chunks=len(chunks),
        hits=hits,
    )
