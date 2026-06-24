import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Returned for every document read operation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_filename: str
    file_size: int
    file_type: str
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated wrapper returned by GET /api/documents."""
    items: list[DocumentResponse]
    total: int
    page: int
    limit: int
