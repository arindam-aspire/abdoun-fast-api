from __future__ import annotations

import logging

from app.services.notifications.email.base import EmailProvider

logger = logging.getLogger(__name__)


class LogEmailProvider(EmailProvider):
    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> None:
        logger.info(
            "email_notification_log_mode to=%s subject=%s body=%s",
            to_email,
            subject,
            text_body,
        )
        return None
