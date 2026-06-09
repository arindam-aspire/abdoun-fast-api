"""Schemas for recently viewed properties endpoints."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, Field, model_validator

from app.schemas.property import PropertySearchResultExtended


class RecentViewUpsertRequest(BaseModel):
    """Request body for adding/updating a recent property view.

    Provide ``property_id`` and/or ``property_hash_id``. When both are sent, ``property_id`` wins.
    """

    property_id: uuid.UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("property_id", "propertyId"),
        description="Canonical property UUID (preferred when both identifiers are sent).",
    )
    property_hash_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("property_hash_id", "propertyHashId"),
        description="Numeric public property id (properties_normalized.property_hash).",
    )

    @model_validator(mode="after")
    def require_property_identifier(self) -> "RecentViewUpsertRequest":
        if self.property_id is None and self.property_hash_id is None:
            raise ValueError("Provide property_id or property_hash_id")
        return self


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
