"""Schemas for location-aware property search and autocomplete."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.property import PropertySearchResponse, PropertySearchResultExtended


class LocationAutocompleteItem(BaseModel):
    name: str
    latitude: float
    longitude: float
    source: str = Field(description="local | nominatim")
    city: Optional[str] = None
    area: Optional[str] = None


class LocationAutocompleteResponse(BaseModel):
    items: list[LocationAutocompleteItem]


class PropertyLocationSearchResultExtended(PropertySearchResultExtended):
    """Search result row with optional distance when a geo filter is applied."""

    distance_km: Optional[float] = None


class PropertyLocationSearchResponse(BaseModel):
    items: list[PropertyLocationSearchResultExtended]
    total: int
    page: int
    pageSize: int
    search_center: Optional[dict[str, float]] = None
