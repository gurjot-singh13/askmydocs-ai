import logging
import uuid

from models.schemas.chunk import Chunk, ChunkingResult
from models.schemas.parser import ExtractionResult

logger = logging.getLogger(__name__)

# ── Default chunking parameters ──────────────────────────────────────────────
DEFAULT_CHUNK_SIZE = 800     # characters
DEFAULT_OVERLAP    = 100     # characters


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Slide a window of `chunk_size` characters over `text` with a step of
    `chunk_size - overlap` characters, returning the list of raw text windows.

    Rules:
    - Windows are taken on character boundaries (no token-level splitting here;
      that is the job of the embedding model's tokenizer in Phase 3B).
    - If the remaining tail is shorter than `chunk_size` it is kept as-is,
      provided it contains at least one non-whitespace character.
    - A step of 1 is enforced as a floor so the loop always terminates even
      if someone passes overlap >= chunk_size.

    Args:
        text:       The full concatenated document text to split.
        chunk_size: Maximum number of characters per chunk.
        overlap:    Number of trailing characters from the previous chunk
                    repeated at the start of the next chunk.

    Returns:
        Ordered list of chunk strings.  May be empty if `text` is blank.
    """
    text = text.strip()
    if not text:
        return []

    step = max(1, chunk_size - overlap)
    windows: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        window = text[start:end]

        # Only keep windows that have meaningful content
        if window.strip():
            windows.append(window)

        start += step

    return windows


def chunk_document(
    extraction: ExtractionResult,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> ChunkingResult:
    """
    Convert an ExtractionResult into an ordered list of text chunks.

    The strategy is intentionally simple for Phase 3A:

    1. Concatenate text from every page in reading order, separated by a
       single newline so page boundaries don't run words together.
    2. Slide a fixed-size character window over the full text.
    3. Return every non-empty window as a Chunk.

    No sentence-boundary detection, no token counting, no semantic splitting —
    those belong in later optimisation phases.  This baseline is correct,
    deterministic, and fast.

    Args:
        extraction: ExtractionResult returned by parser_service.extract_pdf_text().
        chunk_size: Target character window size.  Defaults to 800.
        overlap:    Characters of overlap between consecutive chunks.
                    Must be less than chunk_size.  Defaults to 100.

    Returns:
        ChunkingResult with all chunks in order.

    Raises:
        ValueError: if overlap >= chunk_size (would cause infinite loop).
    """
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )

    # Step 1 — concatenate all page text in order
    full_text = "\n".join(page.text for page in extraction.pages)

    # Step 2 — split into windows
    raw_windows = _split_text(full_text, chunk_size, overlap)

    # Step 3 — wrap in Chunk models with 0-based index
    chunks: list[Chunk] = [
        Chunk(
            chunk_index=i,
            text=window,
            char_count=len(window),
        )
        for i, window in enumerate(raw_windows)
    ]

    total_chars = sum(c.char_count for c in chunks)

    logger.info(
        "Chunked document_id=%s into %d chunks "
        "(chunk_size=%d, overlap=%d, total_chars=%d)",
        extraction.document_id,
        len(chunks),
        chunk_size,
        overlap,
        total_chars,
    )

    return ChunkingResult(
        document_id=extraction.document_id,
        chunk_size=chunk_size,
        overlap=overlap,
        total_chunks=len(chunks),
        total_chars=total_chars,
        chunks=chunks,
    )
