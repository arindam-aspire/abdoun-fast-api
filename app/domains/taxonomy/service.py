"""Refactored taxonomy service preserving v1 response contracts."""

from __future__ import annotations

from app.domains.taxonomy.repository import TaxonomyRepository


class TaxonomyService:
    def __init__(self, repository: TaxonomyRepository) -> None:
        self._repository = repository

    def get_location_taxonomy(self) -> dict:
        cities = self._repository.list_active_cities()
        areas = self._repository.list_active_areas()
        areas_by_city: dict[int, list[dict[str, object]]] = {}
        for area in areas:
            areas_by_city.setdefault(area.city_id, []).append({"id": area.id, "name": area.name})

        data = [{"id": city.id, "name": city.name, "areas": areas_by_city.get(city.id, [])} for city in cities]
        return {"data": data, "total": len(data)}

    def get_property_taxonomy(self) -> dict:
        categories = self._repository.list_active_categories()
        property_types = self._repository.list_active_property_types()
        types_by_category: dict[int, list[dict[str, object]]] = {}
        for item in property_types:
            types_by_category.setdefault(item.category_id, []).append(
                {
                    "id": item.id,
                    "category_id": item.category_id,
                    "name": item.name,
                    "slug": item.slug,
                }
            )

        data = [
            {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "property_types": types_by_category.get(category.id, []),
            }
            for category in categories
        ]
        return {"data": data, "total": len(data)}

