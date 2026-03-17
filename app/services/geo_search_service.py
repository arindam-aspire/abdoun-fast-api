"""
Geo (spatial) property search service.
Uses PropertyRepository for DB access; builds response DTOs.
"""

from __future__ import annotations

import json
from typing import List

from app.repositories.property_repository import PropertyRepository
from app.schemas.property import (
    PropertyListResponse,
    PropertySearchRequest,
    PropertySearchResult,
)
from app.models.property_normalized import PropertyNormalized as Property


class GeoSearchService:
    """Service for geo (bounds/polygon) property search. No DB in router."""

    def __init__(self, repository: PropertyRepository) -> None:
        self._repo = repository

    def search(self, request: PropertySearchRequest) -> PropertyListResponse:
        bounds = None
        polygon_geojson = None
        if request.mode == "bounds" and request.bounds:
            b = request.bounds
            bounds = (b.min_lng, b.min_lat, b.max_lng, b.max_lat)
        elif request.mode == "polygon" and request.polygon:
            polygon_geojson = json.dumps(request.polygon.geojson)

        properties: List[Property] = self._repo.geo_search(
            bounds=bounds,
            polygon_geojson=polygon_geojson,
            limit=request.limit,
        )
        items = [PropertySearchResult.from_orm_obj(p) for p in properties]
        return PropertyListResponse(items=items, total=len(items))
