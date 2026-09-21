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
        from_email: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        # Do not log bodies — they may contain OTPs, reset links, or other secrets.
        logger.info(
            "email_notification_log_mode to=%s subject=%s from=%s has_html=%s",
            to_email,
            subject,
            from_email or "",
            bool(html_body),
        )
        return None
