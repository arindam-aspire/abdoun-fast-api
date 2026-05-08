"""Repository for notification preferences (Phase 1)."""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.notification_preference import NotificationPreference


class NotificationPreferencesRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # Generic helpers -----------------------------------------------------

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

    # Operations ----------------------------------------------------------

    def get_by_user_and_type(
        self,
        *,
        user_id: uuid.UUID,
        notification_type: str,
    ) -> Optional[NotificationPreference]:
        stmt: Select = select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_for_user(self, *, user_id: uuid.UUID) -> Sequence[NotificationPreference]:
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        return self._db.execute(stmt).scalars().all()

    def upsert(
        self,
        *,
        user_id: uuid.UUID,
        notification_type: str,
        enabled: bool,
    ) -> NotificationPreference:
        existing = self.get_by_user_and_type(user_id=user_id, notification_type=notification_type)
        if existing:
            existing.enabled = enabled
            return existing
        row = NotificationPreference(user_id=user_id, notification_type=notification_type, enabled=enabled)
        self._db.add(row)
        return row

