"""Pydantic schemas for user saved searches."""
import uuid
from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel

from app.schemas.property import PropertySearchResultExtended


class SavedSearchCreateRequest(BaseModel):
    name: str
    search_criteria: Dict[str, Any]
    notification_enabled: bool = False


class SavedSearchBulkCreateRequest(BaseModel):
    items: List[SavedSearchCreateRequest]


class SavedSearchUpdateRequest(BaseModel):
    name: str | None = None
    search_criteria: Dict[str, Any] | None = None
    notification_enabled: bool | None = None


class SavedSearchResponse(BaseModel):
    id: uuid.UUID
    name: str
    search_criteria: Dict[str, Any]
    query_string: str
    notification_enabled: bool
    last_run_at: datetime | None = None


class SavedSearchListResponse(BaseModel):
    items: List[SavedSearchResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool


class SavedSearchExecutionResponse(BaseModel):
    items: List[PropertySearchResultExtended]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool

