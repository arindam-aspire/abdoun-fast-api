"""Schemas for recently viewed properties endpoints."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.property import PropertySearchResultExtended


class RecentViewUpsertRequest(BaseModel):
    """Request body for adding/updating a recent property view."""

    property_id: uuid.UUID = Field(..., description="Property identifier")


class RecentViewItem(BaseModel):
    """Recently viewed row payload aligned with favorites response style."""

    id: uuid.UUID
    user_id: uuid.UUID
    property_hash: int
    property_id: uuid.UUID
    viewed_at: datetime
    property: PropertySearchResultExtended


class RecentViewsListResponse(BaseModel):
    """Container response for recent views list."""

    items: List[RecentViewItem]
    total: int
