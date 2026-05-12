"""Notification ORM model (Phase 1: in-app notifications persisted in PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.property import Base

FK_USERS_ID = "users.id"


class Notification(Base):
    """In-app notification stored for a recipient user."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_USERS_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_USERS_ID, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    type_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Routing / analytics (mirrors domain event); backfilled from type_key for legacy rows.
    event_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Idempotency: duplicate key → skip insert (retries, double-submit).
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)

    # Client deep-link (also mirrored in data for backward compatibility).
    action_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


Index("idx_notifications_recipient", Notification.recipient_user_id)
Index("idx_notifications_unread", Notification.recipient_user_id, Notification.is_read)
Index("idx_notifications_created", Notification.created_at.desc())

