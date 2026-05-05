"""Refactored taxonomy repository backed by shared ORM models."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.property_normalized import Area, City, PropertyCategory, PropertyType
from app.repositories.location_repository import LocationRepository
from app.repositories.property_taxonomy_repository import PropertyTaxonomyRepository


class TaxonomyRepository:
    def __init__(self, db: Session) -> None:
        self._location_repo = LocationRepository(db)
        self._taxonomy_repo = PropertyTaxonomyRepository(db)

    def list_active_cities(self) -> list[City]:
        return self._location_repo.list_active_cities()

    def list_active_areas(self) -> list[Area]:
        return self._location_repo.list_active_areas(city_name=None)

    def list_active_categories(self) -> list[PropertyCategory]:
        return self._taxonomy_repo.list_active_categories()

    def list_active_property_types(self) -> list[PropertyType]:
        return self._taxonomy_repo.list_active_property_types(category_id=None)

