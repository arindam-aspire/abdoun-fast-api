"""Repository for admin write operations on properties (assignment, audit fields)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.property_normalized import PropertyNormalized
from app.models.user import User


class PropertyAdminRepository:
    """Write-side repository for property admin operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_property(self, property_id: uuid.UUID) -> PropertyNormalized | None:
        stmt = select(PropertyNormalized).where(PropertyNormalized.id == property_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_with_roles(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = (
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .options(selectinload(User.roles))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

