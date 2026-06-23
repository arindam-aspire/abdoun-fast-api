from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.live_schema import Notification

logger = logging.getLogger(__name__)


def create_in_app_notification(
    db: Session,
    *,
    recipient_user_id: UUID,
    type_key: str,
    title: str,
    message: str,
    actor_user_id: UUID | None = None,
    data: dict[str, Any] | None = None,
    event_type: str | None = None,
    action_url: str | None = None,
    idempotency_key: str | None = None,
) -> Notification:
    notification = Notification(
        id=uuid4(),
        recipient_user_id=recipient_user_id,
        actor_user_id=actor_user_id,
        type_key=type_key,
        title=title,
        message=message,
        data=data,
        event_type=event_type,
        action_url=action_url,
        idempotency_key=idempotency_key,
    )
    db.add(notification)
    return notification


def send_email_notification(*, to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    if settings.notification_email_mode == "log":
        logger.info("email_notification_log_mode to=%s subject=%s body=%s", to_email, subject, body)
        return
    raise NotImplementedError("Email gateway mode is not configured")


def send_sms_notification(*, to_phone: str, body: str) -> None:
    settings = get_settings()
    if settings.notification_sms_mode == "log":
        logger.info("sms_notification_log_mode to=%s body=%s", to_phone, body)
        return
    raise NotImplementedError("SMS gateway mode is not configured")
