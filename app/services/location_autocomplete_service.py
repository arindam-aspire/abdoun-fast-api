"""Location autocomplete: local DB + OpenStreetMap Nominatim."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.property_repository import PropertyRepository
from app.schemas.property_location_search import (
    LocationAutocompleteItem,
    LocationAutocompleteResponse,
)
from app.services.geocoding import GeocodingService
from app.services.nominatim_autocomplete import nominatim_autocomplete_service
from app.utils.responses import StandardResponse, create_success_response


class LocationAutocompleteService:
    def __init__(self, db: Session) -> None:
        self._repo = PropertyRepository(db)
        self._geocoder = GeocodingService()

    def autocomplete(self, query: str, *, limit: int = 5) -> StandardResponse[LocationAutocompleteResponse]:
        text = (query or "").strip()
        if len(text) < 2:
            return create_success_response(
                data=LocationAutocompleteResponse(items=[]),
                message=None,
            )

        items: list[LocationAutocompleteItem] = []
        seen: set[str] = set()

        for row in self._repo.search_local_locations(query=text, limit=limit):
            label = row["name"]
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            coords = self._geocoder.get_coordinates(label)
            if coords:
                lon, lat = coords
                items.append(
                    LocationAutocompleteItem(
                        name=label,
                        latitude=lat,
                        longitude=lon,
                        source="local",
                        city=row.get("city") or None,
                        area=row.get("area") or None,
                    )
                )

        remaining = max(0, limit - len(items))
        if remaining:
            for hit in nominatim_autocomplete_service.search(text, limit=remaining):
                display = str(hit.get("display_name") or "").strip()
                if not display:
                    continue
                key = display.lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    lat = float(hit.get("lat"))
                    lon = float(hit.get("lon"))
                except (TypeError, ValueError):
                    continue
                items.append(
                    LocationAutocompleteItem(
                        name=display,
                        latitude=lat,
                        longitude=lon,
                        source="nominatim",
                    )
                )

        return create_success_response(
            data=LocationAutocompleteResponse(items=items[:limit]),
            message=None,
        )
