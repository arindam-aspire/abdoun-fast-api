from typing import List, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.property_normalized import Area, City


class LocationRepository:
    """Repository for city and area lookups."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active_cities(self) -> List[City]:
        stmt: Select = (
            select(City)
            .where(City.is_active == True)  # noqa: E712
            .order_by(City.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_active_areas(self, *, city_name: Optional[str]) -> List[Area]:
        stmt: Select = select(Area).join(City, Area.city_id == City.id)

        if city_name:
            city_lower = city_name.lower()
            stmt = stmt.where(func.lower(City.name).contains(city_lower))

        stmt = (
            stmt.where(Area.is_active == True)  # noqa: E712
            .order_by(City.name, Area.name)
        )
        return list(self._db.execute(stmt).scalars().all())

