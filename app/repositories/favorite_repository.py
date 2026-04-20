"""Repository for user property favorites persistence and queries."""
import uuid
from typing import List, Optional

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.property_normalized import PropertyNormalized
from app.models.user_property_favorite import UserPropertyFavorite


class FavoriteRepository:
    """Repository for favorites CRUD and validation queries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_property_by_id(self, property_id: uuid.UUID) -> Optional[PropertyNormalized]:
        stmt: Select = (
            select(PropertyNormalized)
            .options(
                joinedload(PropertyNormalized.category),
                joinedload(PropertyNormalized.type),
                joinedload(PropertyNormalized.city),
                joinedload(PropertyNormalized.area_rel),
                joinedload(PropertyNormalized.translations),
            )
            .where(PropertyNormalized.id == property_id)
        )
        return self._db.execute(stmt).unique().scalar_one_or_none()

    def find_property_uuid_by_hash(self, property_hash: int) -> Optional[uuid.UUID]:
        stmt: Select = (
            select(PropertyNormalized.id)
            .where(PropertyNormalized.property_hash == property_hash)
            .order_by(PropertyNormalized.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalars().first()

    def list_properties_by_ids(
        self, property_ids: List[uuid.UUID]
    ) -> List[PropertyNormalized]:
        if not property_ids:
            return []
        stmt: Select = (
            select(PropertyNormalized)
            .options(
                joinedload(PropertyNormalized.category),
                joinedload(PropertyNormalized.type),
                joinedload(PropertyNormalized.city),
                joinedload(PropertyNormalized.area_rel),
                joinedload(PropertyNormalized.translations),
            )
            .where(PropertyNormalized.id.in_(property_ids))
        )
        return list(self._db.execute(stmt).unique().scalars().all())

    def get_favorite_by_user_and_property(
        self, *, user_id: uuid.UUID, property_id: uuid.UUID
    ) -> Optional[UserPropertyFavorite]:
        stmt: Select = select(UserPropertyFavorite).where(
            and_(
                UserPropertyFavorite.user_id == user_id,
                UserPropertyFavorite.property_id == property_id,
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_favorite_property_ids(
        self, *, user_id: uuid.UUID, property_ids: List[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not property_ids:
            return set()
        stmt: Select = select(UserPropertyFavorite.property_id).where(
            and_(
                UserPropertyFavorite.user_id == user_id,
                UserPropertyFavorite.property_id.in_(property_ids),
            )
        )
        return set(self._db.execute(stmt).scalars().all())

    def create_favorite(self, favorite: UserPropertyFavorite) -> UserPropertyFavorite:
        self._db.add(favorite)
        return favorite

    def list_user_favorites(self, *, user_id: uuid.UUID) -> List[UserPropertyFavorite]:
        stmt: Select = (
            select(UserPropertyFavorite)
            .options(
                joinedload(UserPropertyFavorite.property).joinedload(
                    PropertyNormalized.category
                ),
                joinedload(UserPropertyFavorite.property).joinedload(
                    PropertyNormalized.type
                ),
                joinedload(UserPropertyFavorite.property).joinedload(
                    PropertyNormalized.city
                ),
                joinedload(UserPropertyFavorite.property).joinedload(
                    PropertyNormalized.area_rel
                ),
                joinedload(UserPropertyFavorite.property).joinedload(
                    PropertyNormalized.translations
                ),
            )
            .where(UserPropertyFavorite.user_id == user_id)
            .order_by(UserPropertyFavorite.created_at.desc())
        )
        return list(self._db.execute(stmt).unique().scalars().all())

    def count_user_favorites(self, *, user_id: uuid.UUID) -> int:
        stmt: Select = select(func.count(UserPropertyFavorite.id)).where(
            UserPropertyFavorite.user_id == user_id
        )
        total = self._db.execute(stmt).scalar()
        return int(total or 0)

    def delete_favorite(self, favorite: UserPropertyFavorite) -> None:
        self._db.delete(favorite)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

