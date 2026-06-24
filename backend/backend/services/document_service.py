import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.exceptions import DocumentNotFoundException, ForbiddenException
from models.db.document import Document
from models.schemas.document import DocumentListResponse, DocumentResponse

logger = logging.getLogger(__name__)

# Allowed MIME types mapped to the canonical extension stored in the DB
_ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}

# Extra safety net: also match on file extension when content-type is unreliable
_ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx", ".txt"}


def _resolve_file_type(upload: UploadFile) -> str:
    """
    Return the canonical file type string ('pdf', 'docx', 'txt').
    Checks content_type first, falls back to file extension.
    Raises ValueError if the file is not an accepted type.
    """
    if upload.content_type in _ALLOWED_TYPES:
        return _ALLOWED_TYPES[upload.content_type]

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix in _ALLOWED_EXTENSIONS:
        return suffix.lstrip(".")

    raise ValueError(
        f"Unsupported file type. Accepted types: PDF, DOCX, TXT. "
        f"Received content-type='{upload.content_type}', filename='{upload.filename}'"
    )


def _build_storage_path(user_id: uuid.UUID, document_id: uuid.UUID, file_type: str) -> Path:
    """
    Return the absolute path where this file will be written.
    Layout: {UPLOAD_DIR}/{user_id}/{document_id}.{file_type}
    Keeps each user's files in a dedicated directory to avoid name collisions.
    """
    user_dir = Path(settings.UPLOAD_DIR) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"{document_id}.{file_type}"


def get_storage_path(user_id: uuid.UUID, document) -> Path:
    """
    Reconstruct the absolute path to a document's file on disk.

    Accepts either a Document ORM object or a DocumentResponse — both expose
    `.filename`. Uses the same layout convention as `_build_storage_path`:
    {UPLOAD_DIR}/{user_id}/{filename}
    """
    return Path(settings.UPLOAD_DIR) / str(user_id) / document.filename


async def upload_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    upload: UploadFile,
) -> DocumentResponse:
    """
    Persist the uploaded file to local storage and record metadata in PostgreSQL.

    Steps:
    1. Validate file type.
    2. Enforce max file size by reading the stream in chunks.
    3. Write bytes to disk under uploads/{user_id}/{doc_id}.{ext}.
    4. Insert a Document row in PostgreSQL.
    5. Return the document metadata.

    Raises:
        ValueError: unsupported file type or file exceeds size limit.
    """
    file_type = _resolve_file_type(upload)

    document_id = uuid.uuid4()
    storage_path = _build_storage_path(user_id, document_id, file_type)

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    total_bytes = 0
    chunks: list[bytes] = []

    # Read in 1 MB chunks to avoid loading the whole file into memory at once
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise ValueError(
                f"File exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB"
            )
        chunks.append(chunk)

    if total_bytes == 0:
        raise ValueError("Uploaded file is empty")

    # Write to disk
    storage_path.write_bytes(b"".join(chunks))
    logger.info("Saved file to %s (%d bytes)", storage_path, total_bytes)

    # Persist metadata
    document = Document(
        id=document_id,
        user_id=user_id,
        filename=str(storage_path.name),
        original_filename=upload.filename or "unknown",
        file_size=total_bytes,
        file_type=file_type,
        storage_path=str(storage_path),
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    return DocumentResponse.model_validate(document)


async def list_documents(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int,
    limit: int,
) -> DocumentListResponse:
    """
    Return a paginated list of documents owned by the given user.
    Results are ordered newest-first.
    """
    offset = (page - 1) * limit

    # Total count for pagination metadata
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.user_id == user_id)
    )
    total = count_result.scalar_one()

    # Paginated rows
    rows_result = await db.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    documents = rows_result.scalars().all()

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        page=page,
        limit=limit,
    )


async def get_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DocumentResponse:
    """
    Return a single document by ID.

    Raises DocumentNotFoundException if the document does not exist.
    Raises ForbiddenException if the document belongs to a different user.
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise DocumentNotFoundException

    if document.user_id != user_id:
        # Return 404 rather than 403 to avoid leaking document existence to
        # users who don't own it — consistent with security best practice
        raise DocumentNotFoundException

    return DocumentResponse.model_validate(document)


async def delete_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Delete a document record from PostgreSQL and remove the file from disk.

    Raises DocumentNotFoundException if the document does not exist or is
    owned by a different user.
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if document is None or document.user_id != user_id:
        raise DocumentNotFoundException

    # Remove from disk first — if this fails, the DB row is preserved (safe)
    file_path = Path(document.storage_path)
    if file_path.exists():
        file_path.unlink()
        logger.info("Deleted file %s", file_path)
    else:
        logger.warning("File not found on disk during delete: %s", file_path)

    await db.delete(document)
    await db.flush()
