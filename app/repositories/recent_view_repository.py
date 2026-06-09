"""Repository for recently viewed properties persistence operations."""

import uuid
from typing import List

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, joinedload

from app.models.property_normalized import PropertyNormalized
from app.models.recently_viewed_property import RecentlyViewedProperty
from app.models.user import User


class RecentViewRepository:
    """Persistence layer for recent view upsert/list/clear operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def ensure_user_exists_and_lock(self, user_id: uuid.UUID) -> bool:
        """Lock user row to serialize concurrent updates per user."""
        stmt = select(User.id).where(User.id == user_id).with_for_update()
        return self._db.execute(stmt).scalar_one_or_none() is not None

    def property_exists(self, property_id: uuid.UUID) -> bool:
        """Check if referenced property exists."""
        stmt = select(PropertyNormalized.id).where(PropertyNormalized.id == property_id)
        return self._db.execute(stmt).scalar_one_or_none() is not None

    def upsert_recent_view(self, *, user_id: uuid.UUID, property_id: uuid.UUID) -> None:
        """Upsert one recent view row and update viewed_at when duplicate."""
        self._db.execute(
            text(
                """
                INSERT INTO recently_viewed_properties (id, user_id, property_id, viewed_at)
                VALUES (:id, :user_id, :property_id, NOW())
                ON CONFLICT (user_id, property_id)
                DO UPDATE SET viewed_at = EXCLUDED.viewed_at
                """
            ),
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "property_id": property_id,
            },
        )

    def trim_to_limit(self, *, user_id: uuid.UUID, limit: int = 10) -> None:
        """Keep only latest N rows by viewed_at for a user."""
        self._db.execute(
            text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY user_id
                            ORDER BY viewed_at DESC, id DESC
                        ) AS rn
                    FROM recently_viewed_properties
                    WHERE user_id = :user_id
                )
                DELETE FROM recently_viewed_properties AS r
                USING ranked
                WHERE r.id = ranked.id
                  AND ranked.rn > :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )

    def list_recent_views(self, *, user_id: uuid.UUID, limit: int = 10) -> List[RecentlyViewedProperty]:
        """List latest recent views with joined property rows (deleted properties excluded)."""
        stmt = (
            select(RecentlyViewedProperty)
            .join(PropertyNormalized, RecentlyViewedProperty.property_id == PropertyNormalized.id)
            .options(joinedload(RecentlyViewedProperty.property))
            .where(RecentlyViewedProperty.user_id == user_id)
            .order_by(RecentlyViewedProperty.viewed_at.desc(), RecentlyViewedProperty.id.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars().all())

    def clear_recent_views(self, *, user_id: uuid.UUID) -> int:
        """Delete all recent views for a user and return deleted count."""
        stmt = delete(RecentlyViewedProperty).where(RecentlyViewedProperty.user_id == user_id)
        result = self._db.execute(stmt)
        return result.rowcount or 0

    def find_property_uuid_by_hash(self, *, property_hash: int) -> uuid.UUID | None:
        """Resolve hash/id used by frontend to canonical property UUID."""
        stmt = select(PropertyNormalized.id).where(PropertyNormalized.property_hash == property_hash)
        return self._db.execute(stmt).scalar_one_or_none()

    def resolve_property_id(
        self,
        *,
        property_id: uuid.UUID | None,
        property_hash_id: int | None,
    ) -> uuid.UUID | None:
        """Return canonical property UUID; ``property_id`` takes precedence when both are set."""
        if property_id is not None:
            return property_id
        if property_hash_id is not None:
            return self.find_property_uuid_by_hash(property_hash=property_hash_id)
        return None

    def delete_recent_view_by_property_id(self, *, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
        """Delete one recent view entry for a user/property pair."""
        stmt = delete(RecentlyViewedProperty).where(
            RecentlyViewedProperty.user_id == user_id,
            RecentlyViewedProperty.property_id == property_id,
        )
        result = self._db.execute(stmt)
        return result.rowcount or 0

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
