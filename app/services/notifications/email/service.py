from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.notifications.email.base import EmailProvider
from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError
from app.services.notifications.email.log_provider import LogEmailProvider
from app.services.notifications.email.purpose import (
    EmailPurpose,
    normalize_purpose,
    resolve_reply_to_email,
    resolve_sender_email,
)
from app.services.notifications.email.result import EmailSendResult
from app.services.notifications.email.ses_provider import SesEmailProvider
from app.services.notifications.email.templates import build_otp_verification_email, ensure_html_body

logger = logging.getLogger(__name__)


def get_email_provider(mode: str) -> EmailProvider:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "log":
        return LogEmailProvider()
    if normalized_mode == "ses":
        return SesEmailProvider()
    raise EmailConfigurationError(f"Unsupported NOTIFICATION_EMAIL_MODE: {mode}")


class EmailService:
    """Reusable transactional email sender backed by the configured provider (SES or log)."""

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        purpose: EmailPurpose | str = EmailPurpose.GENERAL,
    ) -> EmailSendResult:
        resolved_purpose = normalize_purpose(purpose)
        recipient = (to_email or "").strip()
        if not recipient:
            logger.warning("email_send_skipped purpose=%s reason=missing_recipient", resolved_purpose.value)
            return EmailSendResult(
                success=False,
                error="Recipient email is required",
                purpose=resolved_purpose.value,
            )

        settings = get_settings()
        html = ensure_html_body(text_body, html_body)
        from_email: str | None = None
        from_name = settings.ses_from_name or settings.app_name
        reply_to: str | None = None

        try:
            if settings.notification_email_mode.strip().lower() == "ses":
                from_email, _env_name = resolve_sender_email(settings, resolved_purpose)
                reply_to = resolve_reply_to_email(settings, from_email)
            provider = get_email_provider(settings.notification_email_mode)
            message_id = provider.send(
                to_email=recipient,
                subject=subject,
                text_body=text_body,
                html_body=html,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to,
            )
        except (EmailConfigurationError, EmailDeliveryError) as exc:
            logger.warning(
                "email_send_failed to=%s subject=%s purpose=%s error=%s",
                recipient,
                subject,
                resolved_purpose.value,
                str(exc),
            )
            return EmailSendResult(
                success=False,
                error=str(exc),
                purpose=resolved_purpose.value,
            )
        except Exception:
            logger.exception(
                "email_send_failed to=%s subject=%s purpose=%s error=unexpected",
                recipient,
                subject,
                resolved_purpose.value,
            )
            return EmailSendResult(
                success=False,
                error="Unable to send email notification",
                purpose=resolved_purpose.value,
            )

        return EmailSendResult(
            success=True,
            message_id=message_id or None,
            purpose=resolved_purpose.value,
        )

    def send_otp_verification(
        self,
        *,
        to_email: str,
        otp: str,
        expiry_minutes: int,
        subject: str | None = None,
        app_name: str | None = None,
    ) -> EmailSendResult:
        settings = get_settings()
        email_subject, text_body, html_body = build_otp_verification_email(
            app_name=app_name or settings.app_name,
            otp=otp,
            expiry_minutes=expiry_minutes,
            subject=subject or settings.email_otp_verification_subject,
        )
        return self.send(
            to_email=to_email,
            subject=email_subject,
            text_body=text_body,
            html_body=html_body,
            purpose=EmailPurpose.OTP_VERIFICATION,
        )

    def send_password_reset(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        otp: str | None = None,
        expiry_minutes: int | None = None,
        app_name: str | None = None,
    ) -> EmailSendResult:
        email_subject = subject
        if otp is not None:
            settings = get_settings()
            email_subject, text_body, html_body = build_otp_verification_email(
                app_name=app_name or settings.app_name,
                otp=otp,
                expiry_minutes=expiry_minutes if expiry_minutes is not None else max(settings.auth_otp_ttl_seconds // 60, 1),
                subject=subject or settings.email_otp_verification_subject,
            )
        return self.send(
            to_email=to_email,
            subject=email_subject,
            text_body=text_body,
            html_body=html_body,
            purpose=EmailPurpose.PASSWORD_RESET,
        )

    def send_agent_invitation(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailSendResult:
        return self.send(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            purpose=EmailPurpose.AGENT_INVITATION,
        )

    def send_account_notification(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailSendResult:
        return self.send(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            purpose=EmailPurpose.ACCOUNT_NOTIFICATION,
        )

    def send_general(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailSendResult:
        return self.send(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            purpose=EmailPurpose.GENERAL,
        )


_email_service = EmailService()


def get_email_service() -> EmailService:
    return _email_service


def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    purpose: EmailPurpose | str = EmailPurpose.GENERAL,
) -> str | None:
    """Compatibility wrapper used by existing notification call sites."""
    result = get_email_service().send(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        purpose=purpose,
    )
    return result.message_id if result.success else None
