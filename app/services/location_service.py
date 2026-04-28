"""Service for location reference data (cities with nested areas)."""

from __future__ import annotations

from typing import Dict, List, TypedDict

from app.models.property_normalized import Area, City
from app.repositories.location_repository import LocationRepository


class CityPayload(TypedDict):
    id: int
    name: str


class AreaPayload(TypedDict):
    id: int
    name: str


class CityWithAreasPayload(CityPayload):
    areas: List[AreaPayload]


class LocationService:
    """Service for preparing location responses."""

    def __init__(self, repository: LocationRepository) -> None:
        """Store the location repository for all operations.

        Args:
            repository: LocationRepository instance (request-scoped).
        """
        self._repo = repository

    def get_location_taxonomy(self) -> Dict[str, object]:
        """Return active cities with their active areas in one response."""
        cities: List[City] = self._repo.list_active_cities()
        areas: List[Area] = self._repo.list_active_areas(city_name=None)

        areas_by_city: dict[int, List[AreaPayload]] = {}
        for area in areas:
            areas_by_city.setdefault(area.city_id, []).append({"id": area.id, "name": area.name})

        data: List[CityWithAreasPayload] = [
            {"id": city.id, "name": city.name, "areas": areas_by_city.get(city.id, [])}
            for city in cities
        ]
        return {"data": data, "total": len(data)}

