"""Pydantic schemas for property favorites endpoints."""
import uuid
from typing import List

from pydantic import BaseModel

from app.schemas.property import PropertySearchResultExtended


class FavoriteCreateRequest(BaseModel):
    property_hash: int


class FavoriteBulkCreateRequest(BaseModel):
    property_hashes: List[int]


class FavoriteResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    property_hash: int
    property: PropertySearchResultExtended


class FavoriteBulkSkippedItem(BaseModel):
    property_hash: int
    reason: str


class FavoriteBulkCreateResponse(BaseModel):
    added: List[FavoriteResponse]
    skipped: List[FavoriteBulkSkippedItem]


class FavoriteListResponse(BaseModel):
    items: List[FavoriteResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool

