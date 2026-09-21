from __future__ import annotations

from enum import Enum

from app.core.config import Settings
from app.services.notifications.email.exceptions import EmailConfigurationError


class EmailPurpose(str, Enum):
    OTP_VERIFICATION = "otp_verification"
    PASSWORD_RESET = "password_reset"
    AGENT_INVITATION = "agent_invitation"
    ACCOUNT_NOTIFICATION = "account_notification"
    GENERAL = "general"


# Maps each purpose to (settings attribute, env var name).
_PURPOSE_SENDER: dict[EmailPurpose, tuple[str, str]] = {
    EmailPurpose.OTP_VERIFICATION: ("ses_no_reply_email", "SES_NO_REPLY_EMAIL"),
    EmailPurpose.PASSWORD_RESET: ("ses_no_reply_email", "SES_NO_REPLY_EMAIL"),
    EmailPurpose.AGENT_INVITATION: ("ses_info_email", "SES_INFO_EMAIL"),
    EmailPurpose.ACCOUNT_NOTIFICATION: ("ses_support_email", "SES_SUPPORT_EMAIL"),
    EmailPurpose.GENERAL: ("ses_no_reply_email", "SES_NO_REPLY_EMAIL"),
}

_PURPOSE_ENV_VARS = ("SES_NO_REPLY_EMAIL", "SES_SUPPORT_EMAIL", "SES_INFO_EMAIL")


def normalize_purpose(purpose: EmailPurpose | str | None) -> EmailPurpose:
    if purpose is None:
        return EmailPurpose.GENERAL
    if isinstance(purpose, EmailPurpose):
        return purpose
    normalized = purpose.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "otp": EmailPurpose.OTP_VERIFICATION,
        "verification": EmailPurpose.OTP_VERIFICATION,
        "password": EmailPurpose.PASSWORD_RESET,
        "password_setup": EmailPurpose.PASSWORD_RESET,
        "invitation": EmailPurpose.AGENT_INVITATION,
        "invite": EmailPurpose.AGENT_INVITATION,
        "account": EmailPurpose.ACCOUNT_NOTIFICATION,
        "system": EmailPurpose.GENERAL,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return EmailPurpose(normalized)
    except ValueError:
        return EmailPurpose.GENERAL


def configured_sender_emails(settings: Settings) -> list[str]:
    emails: list[str] = []
    for attr in ("ses_no_reply_email", "ses_support_email", "ses_info_email", "ses_from_email"):
        value = (getattr(settings, attr, None) or "").strip()
        if value:
            emails.append(value)
    return emails


def resolve_sender_email(settings: Settings, purpose: EmailPurpose | str | None) -> tuple[str, str]:
    """Return (from_email, env_var_name) for the given purpose.

    Purpose-specific addresses are required. SES_FROM_EMAIL is only a last-resort
    fallback so existing deployments keep working until they set the new vars.
    """
    resolved_purpose = normalize_purpose(purpose)
    attr, env_name = _PURPOSE_SENDER[resolved_purpose]
    email = (getattr(settings, attr, None) or "").strip()
    if email:
        return email, env_name
    fallback = (settings.ses_from_email or "").strip()
    if fallback:
        return fallback, "SES_FROM_EMAIL"
    raise EmailConfigurationError(
        f"Missing required SES sender for purpose '{resolved_purpose.value}': {env_name}"
    )


def resolve_reply_to_email(settings: Settings, from_email: str) -> str | None:
    support = (settings.ses_support_email or "").strip()
    if support and support.lower() != from_email.strip().lower():
        return support
    return None


def validate_ses_settings(settings: Settings) -> None:
    missing: list[str] = []
    region = (settings.aws_region or "").strip()
    if not region:
        missing.append("AWS_REGION")
    if not configured_sender_emails(settings):
        missing.extend(_PURPOSE_ENV_VARS)
    if missing:
        raise EmailConfigurationError(
            "Missing required SES configuration when NOTIFICATION_EMAIL_MODE=ses: " + ", ".join(missing)
        )
