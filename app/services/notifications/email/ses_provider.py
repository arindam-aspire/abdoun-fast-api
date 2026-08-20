from __future__ import annotations

import logging
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings
from app.services.notifications.email.base import EmailProvider
from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError

logger = logging.getLogger(__name__)

# Required IAM permissions for the runtime role/user:
# - ses:SendEmail
# - ses:SendRawEmail


def _format_source(from_name: str | None, from_email: str) -> str:
    normalized_name = (from_name or "").strip()
    if normalized_name:
        return f"{normalized_name} <{from_email}>"
    return from_email


def validate_ses_settings(settings: Settings) -> None:
    region = (settings.aws_region or "").strip()
    from_email = (settings.ses_from_email or "").strip()
    missing: list[str] = []
    if not region:
        missing.append("AWS_REGION")
    if not from_email:
        missing.append("SES_FROM_EMAIL")
    if missing:
        raise EmailConfigurationError(
            f"Missing required SES configuration when NOTIFICATION_EMAIL_MODE=ses: {', '.join(missing)}"
        )


@lru_cache
def _ses_client():
    settings = get_settings()
    region = (settings.aws_region or "").strip()
    return boto3.client("ses", region_name=region)


class SesEmailProvider(EmailProvider):
    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> str:
        settings = get_settings()
        validate_ses_settings(settings)

        source = _format_source(settings.ses_from_name, settings.ses_from_email.strip())
        body: dict[str, dict[str, str]] = {
            "Text": {"Data": text_body, "Charset": "UTF-8"},
        }
        if html_body:
            body["Html"] = {"Data": html_body, "Charset": "UTF-8"}

        try:
            response = _ses_client().send_email(
                Source=source,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body,
                },
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "ClientError")
            logger.warning(
                "ses_email_send_failed to=%s subject=%s error_code=%s",
                to_email,
                subject,
                error_code,
            )
            raise EmailDeliveryError("Unable to send email notification") from exc
        except BotoCoreError as exc:
            logger.warning(
                "ses_email_send_failed to=%s subject=%s error_type=%s",
                to_email,
                subject,
                type(exc).__name__,
            )
            raise EmailDeliveryError("Unable to send email notification") from exc

        message_id = response.get("MessageId")
        if message_id:
            logger.info(
                "ses_email_sent to=%s subject=%s message_id=%s",
                to_email,
                subject,
                message_id,
            )
        return message_id or ""
