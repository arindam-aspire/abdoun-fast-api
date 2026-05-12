"""Repository for notifications (Phase 1 in-app).

No FastAPI/HTTP concerns; pure DB operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # Generic helpers -----------------------------------------------------

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

    def flush(self) -> None:
        self._db.flush()

    # CRUD ----------------------------------------------------------------

    def create(self, *, notification: Notification) -> Notification:
        self._db.add(notification)
        return notification

    def add_all(self, *, notifications: Sequence[Notification]) -> None:
        if notifications:
            self._db.add_all(notifications)

    def get_by_idempotency_key(self, *, key: str) -> Optional[Notification]:
        stmt: Select = select(Notification).where(Notification.idempotency_key == key).limit(1)
        return self._db.execute(stmt).scalar_one_or_none()

    def list_by_idempotency_keys(self, *, keys: Sequence[str]) -> Sequence[Notification]:
        if not keys:
            return []
        stmt: Select = select(Notification).where(Notification.idempotency_key.in_(keys))
        return self._db.execute(stmt).scalars().all()

    def get_by_id(self, notification_id: uuid.UUID) -> Optional[Notification]:
        stmt: Select = select(Notification).where(Notification.id == notification_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def list_by_ids(self, *, notification_ids: Sequence[uuid.UUID]) -> Sequence[Notification]:
        if not notification_ids:
            return []
        stmt: Select = select(Notification).where(Notification.id.in_(notification_ids))
        return self._db.execute(stmt).scalars().all()

    def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
        include_archived: bool,
    ) -> Tuple[Sequence[Notification], int]:
        where = [Notification.recipient_user_id == user_id]
        if not include_archived:
            where.append(Notification.archived_at.is_(None))

        base = select(Notification).where(*where)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = int(self._db.execute(count_stmt).scalar_one() or 0)

        stmt = (
            base.order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = self._db.execute(stmt).scalars().all()
        return items, total

    def unread_count(self, *, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Notification).where(
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
            Notification.archived_at.is_(None),
        )
        return int(self._db.execute(stmt).scalar_one() or 0)

    def mark_as_read(self, *, notification_id: uuid.UUID, read_at: datetime) -> bool:
        stmt = (
            update(Notification)
            .where(Notification.id == notification_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=read_at)
        )
        res = self._db.execute(stmt)
        return bool(res.rowcount and res.rowcount > 0)

    def mark_all_as_read(self, *, user_id: uuid.UUID, read_at: datetime) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
                Notification.archived_at.is_(None),
            )
            .values(is_read=True, read_at=read_at)
        )
        res = self._db.execute(stmt)
        return int(res.rowcount or 0)

    def archive(self, *, notification_id: uuid.UUID, archived_at: datetime) -> bool:
        stmt = (
            update(Notification)
            .where(Notification.id == notification_id, Notification.archived_at.is_(None))
            .values(archived_at=archived_at)
        )
        res = self._db.execute(stmt)
        return bool(res.rowcount and res.rowcount > 0)

    def archive_many(self, *, notification_ids: Sequence[uuid.UUID], archived_at: datetime) -> int:
        if not notification_ids:
            return 0
        stmt = (
            update(Notification)
            .where(
                Notification.id.in_(notification_ids),
                Notification.archived_at.is_(None),
            )
            .values(archived_at=archived_at)
        )
        res = self._db.execute(stmt)
        return int(res.rowcount or 0)

    def hard_delete(self, *, notification_id: uuid.UUID) -> bool:
        stmt = delete(Notification).where(Notification.id == notification_id)
        res = self._db.execute(stmt)
        return bool(res.rowcount and res.rowcount > 0)

    def hard_delete_many(self, *, notification_ids: Sequence[uuid.UUID]) -> int:
        if not notification_ids:
            return 0
        stmt = delete(Notification).where(Notification.id.in_(notification_ids))
        res = self._db.execute(stmt)
        return int(res.rowcount or 0)

    def unarchive(self, *, notification_id: uuid.UUID) -> bool:
        stmt = (
            update(Notification)
            .where(Notification.id == notification_id, Notification.archived_at.is_not(None))
            .values(archived_at=None)
        )
        res = self._db.execute(stmt)
        return bool(res.rowcount and res.rowcount > 0)

    def unarchive_many(self, *, notification_ids: Sequence[uuid.UUID]) -> int:
        if not notification_ids:
            return 0
        stmt = (
            update(Notification)
            .where(
                Notification.id.in_(notification_ids),
                Notification.archived_at.is_not(None),
            )
            .values(archived_at=None)
        )
        res = self._db.execute(stmt)
        return int(res.rowcount or 0)

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)

