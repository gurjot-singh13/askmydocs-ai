import logging
import threading

from sentence_transformers import SentenceTransformer

from models.schemas.chunk import ChunkingResult
from models.schemas.embedding import ChunkEmbedding, EmbeddingResult

logger = logging.getLogger(__name__)

# ── Model configuration ──────────────────────────────────────────────────────
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384   # fixed output size of bge-small-en-v1.5
PREVIEW_DIMS = 8            # number of dimensions returned in API responses

# ── Lazy, thread-safe singleton ──────────────────────────────────────────────
# Loading the model reads weights from disk/network and takes a few seconds.
# We load it once per process and reuse it across requests rather than
# re-instantiating SentenceTransformer on every call.
_model: SentenceTransformer | None = None
_model_lock = threading.Lock()


def _get_model() -> SentenceTransformer:
    """Return the shared SentenceTransformer instance, loading it on first use."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # re-check inside the lock (double-checked locking)
                logger.info("Loading embedding model: %s", MODEL_NAME)
                _model = SentenceTransformer(MODEL_NAME)
                logger.info(
                    "Embedding model loaded. dimension=%d",
                    _model.get_sentence_embedding_dimension(),
                )
    return _model


def embed_chunks(texts: list[str]) -> list[list[float]]:
    """
    Encode a list of chunk texts into dense embedding vectors.

    Uses bge-small-en-v1.5 in its default (non-instruction-prefixed) mode,
    which is appropriate for embedding the documents/passages side of a
    retrieval pipeline. Query-side embedding in the future retrieval phase
    will prepend the BGE query instruction prefix — that is out of scope here.

    Args:
        texts: Ordered list of raw chunk strings.

    Returns:
        A list of embedding vectors (each a list[float] of length
        EMBEDDING_DIMENSION), in the same order as `texts`. Returns an
        empty list if `texts` is empty.
    """
    if not texts:
        return []

    model = _get_model()
    # normalize_embeddings=True is the standard setting for BGE models —
    # it L2-normalizes vectors so cosine similarity reduces to a dot product,
    # which is what downstream vector databases (Phase 4B) expect.
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_document(chunking_result: ChunkingResult) -> EmbeddingResult:
    """
    Generate embeddings for every chunk produced by the chunking service.

    Args:
        chunking_result: Output of chunk_service.chunk_document().

    Returns:
        EmbeddingResult containing a preview embedding per chunk plus
        document-level metadata (model name, dimension, chunk count).

    Raises:
        ValueError: if chunking_result.chunks is empty — there is nothing
                    to embed (e.g. the source PDF had no extractable text).
    """
    if not chunking_result.chunks:
        raise ValueError(
            "No chunks to embed — the document produced zero chunks "
            "(it may be empty or contain no extractable text)."
        )

    texts = [chunk.text for chunk in chunking_result.chunks]
    vectors = embed_chunks(texts)

    embeddings: list[ChunkEmbedding] = [
        ChunkEmbedding(
            chunk_index=chunk.chunk_index,
            char_count=chunk.char_count,
            embedding_dimension=len(vector),
            embedding_preview=vector[:PREVIEW_DIMS],
        )
        for chunk, vector in zip(chunking_result.chunks, vectors)
    ]

    logger.info(
        "Embedded document_id=%s: %d chunks -> %d-dim vectors using %s",
        chunking_result.document_id,
        len(embeddings),
        EMBEDDING_DIMENSION,
        MODEL_NAME,
    )

    return EmbeddingResult(
        document_id=chunking_result.document_id,
        model_name=MODEL_NAME,
        embedding_dimension=EMBEDDING_DIMENSION,
        total_chunks=len(embeddings),
        embeddings=embeddings,
    )
