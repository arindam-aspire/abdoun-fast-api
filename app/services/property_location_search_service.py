"""Property search with text + geo (PostgreSQL + Haversine)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.property_repository import PropertyRepository
from app.schemas.property import PropertySearchResultExtended
from app.schemas.property_location_search import (
    PropertyLocationSearchResponse,
    PropertyLocationSearchResultExtended,
)
from app.services.geocoding import GeocodingService
from app.services.media_url_signer import MediaUrlSigner
from app.utils.responses import StandardResponse, create_success_response


class PropertyLocationSearchService:
    """Location-aware property search using PostgreSQL and Haversine distance."""

    def __init__(self, db: Session, *, media_url_signer: MediaUrlSigner | None = None) -> None:
        self._db = db
        self._repo = PropertyRepository(db)
        self._geocoder = GeocodingService()
        self._media_url_signer = media_url_signer
        self._settings = get_settings()

    def _resolve_center(
        self,
        *,
        search: Optional[str],
        lat: Optional[float],
        lng: Optional[float],
    ) -> tuple[Optional[float], Optional[float]]:
        """Search text overrides GPS for the geo filter center (per product rules)."""
        if search and search.strip():
            coords = self._geocoder.get_coordinates(search.strip())
            if coords:
                lon, center_lat = coords
                return center_lat, lon
        if lat is not None and lng is not None:
            return lat, lng
        return None, None

    def fetch_properties(
        self,
        *,
        search: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius: Optional[float] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        type_slug: Optional[str] = None,
        exclusive: Optional[str] = None,
        budget_min: Optional[str] = None,
        budget_max: Optional[str] = None,
        min_price: Optional[str] = None,
        max_price: Optional[str] = None,
        city: Optional[str] = None,
        locations: Optional[str] = None,
        page: int = 1,
        page_size: int = 12,
    ) -> tuple[list[Any], dict[int, Optional[float]], int]:
        """Return properties matching text/geo filters and optional distances."""
        radius_km = float(
            radius if radius is not None else self._settings.property_search_default_radius_km
        )
        center_lat, center_lng = self._resolve_center(search=search, lat=lat, lng=lng)

        sql_filters = self._repo.build_property_filters(
            status=status,
            category=category,
            type_slug=type_slug,
            city=city,
            locations=locations,
            exclusive=exclusive,
            budget_min=budget_min or min_price,
            budget_max=budget_max or max_price,
            min_price=min_price,
            max_price=max_price,
        )

        sql_rows, total = self._repo.search_properties_with_text_and_geo(
            filters=sql_filters,
            search_text=search,
            center_lat=center_lat,
            center_lng=center_lng,
            radius_km=radius_km,
            page=page,
            page_size=page_size,
        )
        properties = [p for p, _ in sql_rows]
        distance_map = {p.property_hash: d for p, d in sql_rows}
        return properties, distance_map, total

    def search(
        self,
        *,
        search: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius: Optional[float] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        type_slug: Optional[str] = None,
        exclusive: Optional[str] = None,
        budget_min: Optional[str] = None,
        budget_max: Optional[str] = None,
        min_price: Optional[str] = None,
        max_price: Optional[str] = None,
        page: int = 1,
        page_size: int = 12,
        lang: Optional[str] = None,
    ) -> StandardResponse[PropertyLocationSearchResponse]:
        properties, distance_map, total = self.fetch_properties(
            search=search,
            lat=lat,
            lng=lng,
            radius=radius,
            status=status,
            category=category,
            type_slug=type_slug,
            exclusive=exclusive,
            budget_min=budget_min,
            budget_max=budget_max,
            min_price=min_price,
            max_price=max_price,
            page=page,
            page_size=page_size,
        )

        owner_map: dict = {}
        try:
            property_ids = [p.id for p in properties if isinstance(getattr(p, "id", None), uuid.UUID)]
            owner_map = self._repo.get_owner_details_by_property_ids(property_ids)
        except Exception:
            owner_map = {}

        items: list[PropertyLocationSearchResultExtended] = []
        for prop in properties:
            base = PropertySearchResultExtended.from_orm_obj(
                prop,
                lang=lang,
                owner_details=owner_map.get(getattr(prop, "id", None), []),
            )
            item = PropertyLocationSearchResultExtended(
                **base.model_dump(),
                distance_km=distance_map.get(prop.property_hash),
            )
            if self._media_url_signer is not None:
                self._media_url_signer.sign_search_result_extended(item)
            items.append(item)

        center_lat, center_lng = self._resolve_center(search=search, lat=lat, lng=lng)
        search_center = None
        if center_lat is not None and center_lng is not None:
            search_center = {"latitude": center_lat, "longitude": center_lng}

        payload = PropertyLocationSearchResponse(
            items=items,
            total=total,
            page=page,
            pageSize=page_size,
            search_center=search_center,
        )
        return create_success_response(data=payload, message=None)
