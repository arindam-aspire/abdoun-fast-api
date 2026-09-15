from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.live_schema import Notification
from app.services.notifications.email.service import send_email

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


def send_email_notification(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> str | None:
    return send_email(
        to_email=to_email,
        subject=subject,
        text_body=body,
        html_body=html_body,
    )


def send_sms_notification(*, to_phone: str, body: str) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.notification_sms_mode == "log":
        logger.info("sms_notification_log_mode to=%s body=%s", to_phone, body)
        return
    logger.warning("sms_notification_skipped mode=%s to=%s", settings.notification_sms_mode, to_phone)
