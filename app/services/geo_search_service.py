"""Geo (spatial) property search: bounds or polygon; uses PropertyRepository, returns PropertyListResponse."""

from __future__ import annotations

import json
from typing import List

from app.repositories.property_repository import PropertyRepository
from app.schemas.property import (
    PropertyListResponse,
    PropertySearchRequest,
    PropertySearchResult,
)
from app.services.media_url_signer import MediaUrlSigner
from app.models.property_normalized import PropertyNormalized as Property


class GeoSearchService:
    """Service for geo (bounds/polygon) property search. No DB in router."""

    def __init__(self, repository: PropertyRepository, *, media_url_signer: MediaUrlSigner | None = None) -> None:
        """Store the property repository for geo queries.

        Args:
            repository: PropertyRepository instance.
            media_url_signer: Optional presigned GET for S3 thumbnails.
        """
        self._repo = repository
        self._media_url_signer = media_url_signer

    def search(self, request: PropertySearchRequest) -> PropertyListResponse:
        """Run geo search by bounds or polygon; return list of PropertySearchResult and total."""
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
        if self._media_url_signer is not None:
            for it in items:
                self._media_url_signer.sign_search_result(it)
        return PropertyListResponse(items=items, total=len(items))
