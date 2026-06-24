import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from dependencies import get_current_active_user
from models.db.user import User
from models.schemas.chunk import ChunkingResult
from models.schemas.document import DocumentListResponse, DocumentResponse
from models.schemas.embedding import EmbeddingResult
from models.schemas.parser import ExtractionResult
from models.schemas.retrieval import SearchResult
from models.schemas.vector_store import IndexResult
from services import (
    chunk_service,
    document_service,
    embedding_service,
    parser_service,
    retrieval_service,
    vector_store_service,
)

router = APIRouter(prefix="/api/documents", tags=["Documents"])


# ── Shared pipeline helper ────────────────────────────────────────────────────

async def _run_pipeline(
    document_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    chunk_size: int,
    overlap: int,
) -> tuple:
    """
    Run parse → chunk → embed for a document and return the full pipeline outputs.

    Returns:
        (document, storage_path, extraction, chunking_result, chunk_vectors)

    Used by /embeddings (Phase 4A, still in-memory) and /index (Phase 5B,
    persists the result to ChromaDB). /search no longer uses this helper —
    see search_document() below, which reads from ChromaDB instead.
    """
    if overlap >= chunk_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"overlap ({overlap}) must be less than chunk_size ({chunk_size})",
        )

    document = await document_service.get_document(db, document_id, current_user.id)

    if document.file_type != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This endpoint only supports PDF files. "
                f"Document type is '{document.file_type}'."
            ),
        )

    storage_path = document_service.get_storage_path(current_user.id, document)

    try:
        extraction = parser_service.extract_pdf_text(storage_path, document.id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        chunking_result = chunk_service.chunk_document(extraction, chunk_size, overlap)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Full 384-dim vectors — not preview-truncated
    chunk_vectors: list[list[float]] = embedding_service.embed_chunks(
        [c.text for c in chunking_result.chunks]
    )

    return document, storage_path, extraction, chunking_result, chunk_vectors


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document (PDF, DOCX, or TXT)",
)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentResponse:
    """
    Upload a single document file.

    - Accepted types: **PDF**, **DOCX**, **TXT**
    - Maximum size: controlled by ``MAX_FILE_SIZE_MB`` in settings (default 50 MB)
    - File is stored at ``uploads/{user_id}/{document_id}.{ext}``
    - Metadata is persisted in PostgreSQL immediately
    """
    try:
        return await document_service.upload_document(db, current_user.id, file)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all documents for the authenticated user",
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentListResponse:
    """Return a paginated list of the authenticated user's documents, newest-first."""
    return await document_service.list_documents(db, current_user.id, page, limit)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single document by ID",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentResponse:
    """
    Return metadata for a single document.

    Returns **404** if the document does not exist or belongs to a different user.
    """
    return await document_service.get_document(db, document_id, current_user.id)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Permanently delete a document, its file from local storage, and any
    vectors indexed for it in ChromaDB.

    Returns **404** if the document does not exist or belongs to a different user.
    Returns **204 No Content** on success.
    """
    document = await document_service.get_document(db, document_id, current_user.id)
    vector_store_service.delete_document_vectors(document.id)
    await document_service.delete_document(db, document_id, current_user.id)


@router.get(
    "/{document_id}/extract",
    response_model=ExtractionResult,
    status_code=status.HTTP_200_OK,
    summary="Extract text from a PDF document (Phase 2A)",
)
async def extract_document_text(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExtractionResult:
    """
    Run PDF text extraction on an already-uploaded document.
    Returns per-page text, page count, and total character count.
    Does **not** persist the extracted text.
    """
    document = await document_service.get_document(db, document_id, current_user.id)

    if document.file_type != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Text extraction is only supported for PDF files. "
                   f"This document is of type '{document.file_type}'.",
        )

    storage_path = document_service.get_storage_path(current_user.id, document)

    try:
        return parser_service.extract_pdf_text(storage_path, document.id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/{document_id}/chunks",
    response_model=ChunkingResult,
    status_code=status.HTTP_200_OK,
    summary="Chunk extracted PDF text (Phase 3A)",
)
async def get_document_chunks(
    document_id: uuid.UUID,
    chunk_size: int = Query(default=800, ge=100, le=4000, description="Maximum characters per chunk"),
    overlap: int = Query(default=100, ge=0, le=400, description="Characters of overlap between consecutive chunks"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChunkingResult:
    """
    Extract text from a PDF and split it into ordered, overlapping chunks.
    Stateless — chunks are **not** persisted.
    """
    if overlap >= chunk_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"overlap ({overlap}) must be less than chunk_size ({chunk_size})",
        )

    document = await document_service.get_document(db, document_id, current_user.id)

    if document.file_type != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chunking is only supported for PDF files. "
                   f"This document is of type '{document.file_type}'.",
        )

    storage_path = document_service.get_storage_path(current_user.id, document)

    try:
        extraction = parser_service.extract_pdf_text(storage_path, document.id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        return chunk_service.chunk_document(extraction, chunk_size, overlap)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/{document_id}/embeddings",
    response_model=EmbeddingResult,
    status_code=status.HTTP_200_OK,
    summary="Generate embeddings for a document's chunks (Phase 4A)",
)
async def get_document_embeddings(
    document_id: uuid.UUID,
    chunk_size: int = Query(default=800, ge=100, le=4000, description="Maximum characters per chunk"),
    overlap: int = Query(default=100, ge=0, le=400, description="Characters of overlap between consecutive chunks"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EmbeddingResult:
    """
    Extract, chunk, and embed a PDF document's text using
    ``BAAI/bge-small-en-v1.5`` (384-dimensional vectors).

    Stateless — embeddings are **not** persisted to ChromaDB by this endpoint.
    Use **POST /{document_id}/index** to persist embeddings for search.
    """
    _, _, _, chunking_result, chunk_vectors = await _run_pipeline(
        document_id, db, current_user, chunk_size, overlap
    )

    from models.schemas.embedding import ChunkEmbedding
    from services.embedding_service import EMBEDDING_DIMENSION, MODEL_NAME, PREVIEW_DIMS

    embeddings = [
        ChunkEmbedding(
            chunk_index=chunk.chunk_index,
            char_count=chunk.char_count,
            embedding_dimension=len(vector),
            embedding_preview=vector[:PREVIEW_DIMS],
        )
        for chunk, vector in zip(chunking_result.chunks, chunk_vectors)
    ]

    return EmbeddingResult(
        document_id=chunking_result.document_id,
        model_name=MODEL_NAME,
        embedding_dimension=EMBEDDING_DIMENSION,
        total_chunks=len(embeddings),
        embeddings=embeddings,
    )


@router.post(
    "/{document_id}/index",
    response_model=IndexResult,
    status_code=status.HTTP_201_CREATED,
    summary="Index a document into ChromaDB (Phase 5B)",
)
async def index_document(
    document_id: uuid.UUID,
    chunk_size: int = Query(default=800, ge=100, le=4000, description="Maximum characters per chunk"),
    overlap: int = Query(default=100, ge=0, le=400, description="Characters of overlap between consecutive chunks"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> IndexResult:
    """
    Parse, chunk, embed, and persist a PDF document's chunks into ChromaDB.

    This is the **write path** for semantic search: after calling this
    endpoint, ``GET /{document_id}/search`` retrieves chunks directly from
    ChromaDB without recomputing embeddings.

    Re-calling this endpoint **replaces** the document's existing vectors —
    useful for re-indexing with a different ``chunk_size``/``overlap``.

    Metadata stored per chunk in ChromaDB:
    ``document_id``, ``chunk_index``, ``char_count``.

    Returns **400** if the document is not a PDF, overlap ≥ chunk_size, or it
    produces zero chunks.
    Returns **404** if the document does not exist or belongs to a different user.
    """
    _, _, _, chunking_result, chunk_vectors = await _run_pipeline(
        document_id, db, current_user, chunk_size, overlap
    )

    from services.embedding_service import MODEL_NAME

    try:
        return vector_store_service.index_document(
            chunking_result=chunking_result,
            chunk_vectors=chunk_vectors,
            model_name=MODEL_NAME,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/{document_id}/search",
    response_model=SearchResult,
    status_code=status.HTTP_200_OK,
    summary="Semantic search over indexed document chunks (Phase 5B)",
)
async def search_document(
    document_id: uuid.UUID,
    query: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Natural-language question or search query",
    ),
    top_k: int = Query(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SearchResult:
    """
    Perform **semantic search over chunks already indexed in ChromaDB**.

    Unlike the Phase 5A in-memory version, this endpoint does **not**
    re-parse, re-chunk, or re-embed the document on every call. It:

    1. Verifies the document exists and belongs to the caller.
    2. Embeds only the query (using the BGE query-instruction prefix).
    3. Queries ChromaDB, scoped to this ``document_id``, for the nearest
       vectors by cosine similarity.
    4. Returns the ``top_k`` most relevant chunks with scores.

    **Prerequisite:** the document must have been indexed first via
    ``POST /{document_id}/index``. Calling search before indexing returns
    a **400** with a message telling you to index first.

    Returns **404** if the document does not exist or belongs to a different user.
    """
    # Ownership check — also confirms the document exists for this user
    await document_service.get_document(db, document_id, current_user.id)

    # Embed only the query — chunk embeddings are NOT regenerated here
    from services.embedding_service import embed_chunks
    from services.retrieval_service import _QUERY_INSTRUCTION

    prefixed_query = _QUERY_INSTRUCTION + query.strip()
    query_vector = embed_chunks([prefixed_query])[0]

    try:
        return vector_store_service.search_indexed(
            document_id=document_id,
            query=query,
            query_vector=query_vector,
            top_k=top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
