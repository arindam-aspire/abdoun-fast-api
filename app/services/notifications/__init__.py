from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.live_schema import Notification
from app.services.notifications.email.purpose import EmailPurpose
from app.services.notifications.email.result import EmailSendResult
from app.services.notifications.email.service import EmailService, get_email_service, send_email

logger = logging.getLogger(__name__)

__all__ = [
    "EmailPurpose",
    "EmailSendResult",
    "EmailService",
    "SmsEligibilityError",
    "create_in_app_notification",
    "get_email_service",
    "is_phone_verified",
    "notify_registered_sms",
    "send_email",
    "send_email_notification",
    "send_registered_sms",
    "send_sms_notification",
]


class SmsEligibilityError(Exception):
    """Raised when an application SMS must not be sent."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


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
    purpose: EmailPurpose | str = EmailPurpose.GENERAL,
) -> str | None:
    return send_email(
        to_email=to_email,
        subject=subject,
        text_body=body,
        html_body=html_body,
        purpose=purpose,
    )


def is_phone_verified(user: object) -> bool:
    """True only when the stored verification flag is explicitly true.

    A phone number on its own is not verification. False, null, and any
    other value are unverified.
    """
    return getattr(user, "is_phone_verified", None) is True


def send_sms_notification(*, to_phone: str, body: str) -> bool:
    """Low-level SMS delivery used for verification codes.

    Application and transactional messages must use send_registered_sms so
    an unverified number cannot receive them.
    """
    from app.services.notifications.sms import deliver_sms

    return deliver_sms(to_phone=to_phone, body=body)


def send_registered_sms(*, user: object, body: str, requested_phone: str | None = None) -> None:
    """Send an application SMS to the user's registered, verified number.

    The destination is always the number stored on the user. A caller-supplied
    number is accepted only when it matches that registered number.
    """
    from app.services.notifications.sms import deliver_sms, phones_match, to_e164_phone

    registered_raw = getattr(user, "phone_number", None)
    registered = to_e164_phone(registered_raw if isinstance(registered_raw, str) else None)
    if not registered:
        raise SmsEligibilityError("phone_missing", "A verified mobile number is required")
    if requested_phone is not None and str(requested_phone).strip():
        if not phones_match(requested_phone, registered):
            raise SmsEligibilityError(
                "phone_not_registered",
                "SMS can only be sent to the registered mobile number",
            )
    if not is_phone_verified(user):
        raise SmsEligibilityError("phone_not_verified", "Mobile number is not verified")
    deliver_sms(to_phone=registered, body=body)


def notify_registered_sms(*, user: object, body: str) -> None:
    """Best-effort application SMS. Ineligible numbers are skipped, not sent."""
    try:
        send_registered_sms(user=user, body=body)
    except SmsEligibilityError as exc:
        logger.info("sms_notification_skipped reason=%s", exc.code)
