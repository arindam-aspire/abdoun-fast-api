"""Repository for property taxonomy lookups (categories and types)."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.property_normalized import PropertyCategory, PropertyType


class PropertyTaxonomyRepository:
    """Repository for property category/type reference data."""

    def __init__(self, db: Session) -> None:
        """Store the database session for all operations.

        Args:
            db: SQLAlchemy Session (request-scoped).
        """
        self._db = db

    def list_active_categories(self) -> List[PropertyCategory]:
        """Return all active property categories ordered by name."""
        stmt: Select = (
            select(PropertyCategory)
            .where(PropertyCategory.is_active.is_(True))
            .order_by(PropertyCategory.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_active_property_types(self, *, category_id: Optional[int]) -> List[PropertyType]:
        """Return active property types ordered by name; optionally filtered by category_id.

        When category_id is provided, results are additionally filtered to types that belong
        to an active category with that id.

        Args:
            category_id: Optional category id to filter by.

        Returns:
            List of PropertyType ORM instances.
        """
        stmt: Select = (
            select(PropertyType)
            .join(PropertyCategory, PropertyType.category_id == PropertyCategory.id)
            .where(PropertyType.is_active.is_(True))
            .where(PropertyCategory.is_active.is_(True))
        )

        if category_id is not None:
            stmt = stmt.where(PropertyType.category_id == category_id)

        stmt = stmt.order_by(PropertyType.name)
        return list(self._db.execute(stmt).scalars().all())

