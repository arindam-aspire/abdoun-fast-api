"""Schemas for GET /properties/my-listings (agent and admin dashboards)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MyListingAgentInfo(BaseModel):
    """Assigned agent on a property (admin view); null when unassigned."""

    id: uuid.UUID
    full_name: str
    email: str
    phone_number: str | None = None


class MyListingItem(BaseModel):
    property_id: uuid.UUID
    property_hash_id: int
    title: str
    status: str = Field(description="One of: Draft, Pending, Active, Rejected, Inactive")
    property_type: str | None = Field(default=None, description="Property type slug")
    created_at: datetime
    updated_at: datetime | None = None
    created_by: uuid.UUID | None = None
    agent: MyListingAgentInfo | None = None


class MyListingsResponse(BaseModel):
    items: list[MyListingItem]
    page: int
    page_size: int
    total_count: int
