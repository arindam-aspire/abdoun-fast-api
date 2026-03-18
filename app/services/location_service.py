"""Service for cities and areas: list active cities/areas with optional city filter; returns payloads for API."""
from typing import Dict, List, Optional, TypedDict

from app.models.property_normalized import Area, City
from app.repositories.location_repository import LocationRepository


class CityPayload(TypedDict):
    id: int
    name: str


class AreaPayload(TypedDict):
    id: int
    name: str
    city_id: int
    city_name: Optional[str]


class LocationService:
    """Service for preparing location responses."""

    def __init__(self, repository: LocationRepository) -> None:
        """Store the location repository for all operations.

        Args:
            repository: LocationRepository instance (request-scoped).
        """
        self._repo = repository

    def list_cities(self) -> Dict[str, object]:
        """Return active cities as {data: [...], total: n}."""
        cities: List[City] = self._repo.list_active_cities()
        data: List[CityPayload] = [
            {"id": city.id, "name": city.name}
            for city in cities
        ]
        return {"data": data, "total": len(cities)}

    def list_areas(self, *, city: Optional[str]) -> Dict[str, object]:
        """Return active areas as {data: [...], total: n}; optionally filter by city name."""
        areas: List[Area] = self._repo.list_active_areas(city_name=city)
        data: List[AreaPayload] = [
            {
                "id": area.id,
                "name": area.name,
                "city_id": area.city_id,
                "city_name": area.city.name if area.city else None,
            }
            for area in areas
        ]
        return {"data": data, "total": len(areas)}

