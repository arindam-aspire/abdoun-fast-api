"""Repository layer for user saved searches and execution queries."""
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session, joinedload

from app.models.property_normalized import PropertyNormalized
from app.models.user_saved_search import UserSavedSearch

ACTIVE_PROPERTY_STATUS_IDS = (1, 5)


class SavedSearchRepository:
    """Repository for saved-search CRUD and result execution."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_saved_search(self, saved_search: UserSavedSearch) -> UserSavedSearch:
        self._db.add(saved_search)
        return saved_search

    def get_saved_search_by_id_for_user(
        self, *, saved_search_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[UserSavedSearch]:
        stmt: Select = select(UserSavedSearch).where(
            and_(
                UserSavedSearch.id == saved_search_id,
                UserSavedSearch.user_id == user_id,
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_saved_searches_for_user(self, *, user_id: uuid.UUID) -> List[UserSavedSearch]:
        stmt: Select = (
            select(UserSavedSearch)
            .where(UserSavedSearch.user_id == user_id)
            .order_by(UserSavedSearch.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_saved_search_names_for_user(self, *, user_id: uuid.UUID) -> set[str]:
        stmt: Select = select(UserSavedSearch.name).where(UserSavedSearch.user_id == user_id)
        return {name for name in self._db.execute(stmt).scalars().all() if name is not None}

    def get_saved_search_by_name_for_user(
        self, *, user_id: uuid.UUID, name: str
    ) -> Optional[UserSavedSearch]:
        stmt: Select = select(UserSavedSearch).where(
            and_(
                UserSavedSearch.user_id == user_id,
                UserSavedSearch.name == name,
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def delete_saved_search(self, saved_search: UserSavedSearch) -> None:
        self._db.delete(saved_search)

    def run_saved_search_query(self, *, criteria: dict[str, Any]) -> List[PropertyNormalized]:
        stmt: Select = (
            select(PropertyNormalized)
            .options(
                joinedload(PropertyNormalized.category),
                joinedload(PropertyNormalized.type),
                joinedload(PropertyNormalized.city),
                joinedload(PropertyNormalized.area_rel),
                joinedload(PropertyNormalized.translations),
            )
            .where(PropertyNormalized.property_status_id.in_(ACTIVE_PROPERTY_STATUS_IDS))
        )

        min_price = criteria.get("min_price")
        max_price = criteria.get("max_price")
        bedrooms = criteria.get("bedrooms")
        bathrooms = criteria.get("bathrooms")
        city_id = criteria.get("city_id")
        location_id = criteria.get("location_id")
        category_id = criteria.get("category_id")
        type_id = criteria.get("type_id")
        is_exclusive = criteria.get("is_exclusive")

        if min_price is not None:
            stmt = stmt.where(PropertyNormalized.price >= float(min_price))
        if max_price is not None:
            stmt = stmt.where(PropertyNormalized.price <= float(max_price))
        if bedrooms is not None:
            stmt = stmt.where(PropertyNormalized.bedrooms >= int(bedrooms))
        if bathrooms is not None:
            stmt = stmt.where(PropertyNormalized.bathrooms >= int(bathrooms))
        if city_id is not None:
            stmt = stmt.where(PropertyNormalized.city_id == int(city_id))
        if location_id is not None:
            stmt = stmt.where(PropertyNormalized.location_id == int(location_id))
        if category_id is not None:
            stmt = stmt.where(PropertyNormalized.category_id == int(category_id))
        if type_id is not None:
            stmt = stmt.where(PropertyNormalized.type_id == int(type_id))
        if is_exclusive is not None:
            stmt = stmt.where(PropertyNormalized.is_exclusive.is_(bool(is_exclusive)))

        stmt = stmt.order_by(PropertyNormalized.created_at.desc())
        return list(self._db.execute(stmt).unique().scalars().all())

    def touch_last_run(self, saved_search: UserSavedSearch) -> None:
        saved_search.last_run_at = datetime.now(timezone.utc)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

