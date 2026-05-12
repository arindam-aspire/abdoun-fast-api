"""Synchronous notification dispatch: domain → registry → validator → persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import uuid

from app.constants.notification_types import NotificationType
from app.models.notification import Notification
from app.services.notification_route_registry import NotificationRouteRegistry
from app.services.notification_service import NotificationCreateInput, NotificationService


@dataclass(frozen=True, slots=True)
class NotificationEmitPayload:
    """One logical notification for one recipient."""

    event_type: str
    type_key: str
    recipient_user_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    recipient_role_names: frozenset[str]
    template_data: Mapping[str, Any]
    idempotency_key: str
    route_context: Mapping[str, Any] | None = None


class NotificationEventEmitter:
    """Single entry point from domain services (no direct NotificationService calls)."""

    def __init__(self, notification_service: NotificationService) -> None:
        self._svc = notification_service

    def _merge_storage_data(self, payload: NotificationEmitPayload) -> dict[str, Any]:
        route_ctx = dict(payload.route_context or {})
        if payload.event_type in (
            NotificationType.AGENT_APPROVED.value,
            NotificationType.AGENT_REJECTED.value,
        ):
            route_ctx.setdefault("agent_user_id", str(payload.recipient_user_id))

        merged_ctx = {**dict(payload.template_data), **route_ctx}
        action_url = NotificationRouteRegistry.resolve_action_url(
            event_type=payload.event_type,
            role_names=payload.recipient_role_names,
            context=merged_ctx,
        )
        data = dict(payload.template_data)
        meta = dict(data["metadata"]) if isinstance(data.get("metadata"), dict) else {}
        meta.setdefault("redirect_path", action_url)
        data["action_url"] = action_url
        data["metadata"] = meta
        return data

    def emit(self, *, payload: NotificationEmitPayload) -> Optional[Notification]:
        data = self._merge_storage_data(payload)
        return self._svc.create_notification(
            input=NotificationCreateInput(
                recipient_user_id=payload.recipient_user_id,
                actor_user_id=payload.actor_user_id,
                event_type=payload.event_type,
                type_key=payload.type_key,
                data=data,
                idempotency_key=payload.idempotency_key,
            )
        )

    def emit_bulk(self, *, payloads: Sequence[NotificationEmitPayload]) -> list[Notification]:
        if not payloads:
            return []
        inputs = [
            NotificationCreateInput(
                recipient_user_id=p.recipient_user_id,
                actor_user_id=p.actor_user_id,
                event_type=p.event_type,
                type_key=p.type_key,
                data=self._merge_storage_data(p),
                idempotency_key=p.idempotency_key,
            )
            for p in payloads
        ]
        return self._svc.create_notifications_bulk(inputs=inputs)
