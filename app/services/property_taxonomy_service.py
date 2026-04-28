"""Service for property taxonomy reference data (categories with nested types)."""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict

from app.models.property_normalized import PropertyCategory, PropertyType
from app.repositories.property_taxonomy_repository import PropertyTaxonomyRepository


class PropertyCategoryPayload(TypedDict):
    id: int
    name: str
    slug: str


class PropertyTypePayload(TypedDict):
    id: int
    category_id: int
    name: str
    slug: str


class PropertyCategoryWithTypesPayload(PropertyCategoryPayload):
    property_types: List[PropertyTypePayload]


class PropertyTaxonomyService:
    """Service for preparing property taxonomy responses."""

    def __init__(self, repository: PropertyTaxonomyRepository) -> None:
        """Store the taxonomy repository for all operations.

        Args:
            repository: PropertyTaxonomyRepository instance (request-scoped).
        """
        self._repo = repository

    def get_property_taxonomy(self) -> Dict[str, object]:
        """Return active categories with their active property types in one response."""
        categories: List[PropertyCategory] = self._repo.list_active_categories()
        types: List[PropertyType] = self._repo.list_active_property_types(category_id=None)

        types_by_category: dict[int, List[PropertyTypePayload]] = {}
        for t in types:
            types_by_category.setdefault(t.category_id, []).append(
                {
                    "id": t.id,
                    "category_id": t.category_id,
                    "name": t.name,
                    "slug": t.slug,
                }
            )

        data: List[PropertyCategoryWithTypesPayload] = [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "property_types": types_by_category.get(c.id, []),
            }
            for c in categories
        ]
        return {"data": data, "total": len(data)}

