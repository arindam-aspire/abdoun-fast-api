"""Realtime notification service (WebSocket delivery only).

This is an additive enhancement: DB remains the source of truth.
All websocket failures must degrade gracefully.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

import anyio

from app.models.notification import Notification
from app.websockets.connection_manager import ConnectionManager


class RealtimeNotificationService:
    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    def notification_created(self, *, notification: Notification, unread_count: int) -> None:
        payload = {
            "event": "notification.created",
            "data": _notification_payload(notification=notification, unread_count=unread_count),
        }
        self._fire_and_forget(user_id=notification.recipient_user_id, payload=payload)

    def notification_read(self, *, notification: Notification, unread_count: int) -> None:
        payload = {
            "event": "notification.read",
            "data": _notification_payload(notification=notification, unread_count=unread_count),
        }
        self._fire_and_forget(user_id=notification.recipient_user_id, payload=payload)

    def notification_archived(self, *, notification: Notification, unread_count: int) -> None:
        payload = {
            "event": "notification.archived",
            "data": _notification_payload(notification=notification, unread_count=unread_count),
        }
        self._fire_and_forget(user_id=notification.recipient_user_id, payload=payload)

    def unread_count_updated(self, *, user_id: uuid.UUID, unread_count: int) -> None:
        payload = {
            "event": "unread_count.updated",
            "data": {"unread_count": unread_count},
        }
        self._fire_and_forget(user_id=user_id, payload=payload)

    def notification_unarchived(self, *, notification: Notification, unread_count: int) -> None:
        payload = {
            "event": "notification.unarchived",
            "data": _notification_payload(notification=notification, unread_count=unread_count),
        }
        self._fire_and_forget(user_id=notification.recipient_user_id, payload=payload)

    def _fire_and_forget(self, *, user_id: uuid.UUID, payload: dict[str, Any]) -> None:
        """Schedule async send without blocking request threads."""
        try:
            anyio.from_thread.run(
                lambda: self._manager.send_to_user(user_id=user_id, message=payload)
            )
        except Exception:
            # Best-effort only: never fail core flows.
            return


def _notification_payload(*, notification: Notification, unread_count: int) -> dict[str, Any]:
    def _iso(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt is not None else None

    return {
        "id": str(notification.id),
        "type_key": notification.type_key,
        "title": notification.title,
        "message": notification.message,
        "is_read": bool(notification.is_read),
        "created_at": _iso(notification.created_at),
        "read_at": _iso(notification.read_at),
        "archived_at": _iso(notification.archived_at),
        "unread_count": int(unread_count),
    }

