from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.notifications.email.base import EmailProvider
from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError
from app.services.notifications.email.log_provider import LogEmailProvider
from app.services.notifications.email.ses_provider import SesEmailProvider

logger = logging.getLogger(__name__)


def get_email_provider(mode: str) -> EmailProvider:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "log":
        return LogEmailProvider()
    if normalized_mode == "ses":
        return SesEmailProvider()
    raise EmailConfigurationError(f"Unsupported NOTIFICATION_EMAIL_MODE: {mode}")


def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> str | None:
    settings = get_settings()
    try:
        provider = get_email_provider(settings.notification_email_mode)
        return provider.send(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    except (EmailConfigurationError, EmailDeliveryError) as exc:
        logger.warning(
            "email_send_failed to=%s subject=%s error=%s",
            to_email,
            subject,
            str(exc),
        )
        return None
