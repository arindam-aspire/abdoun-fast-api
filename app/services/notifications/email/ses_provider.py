from __future__ import annotations

import logging
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.services.notifications.email.base import EmailProvider
from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError
from app.services.notifications.email.purpose import validate_ses_settings as _validate_ses_settings

logger = logging.getLogger(__name__)

# Required IAM permissions for the runtime role/user:
# - ses:SendEmail
# - ses:SendRawEmail

validate_ses_settings = _validate_ses_settings


def _format_source(from_name: str | None, from_email: str) -> str:
    normalized_name = (from_name or "").strip()
    if normalized_name:
        return f"{normalized_name} <{from_email}>"
    return from_email


@lru_cache
def _ses_client():
    # Use the default AWS credential chain (IAM role, instance profile, or env).
    # Never pass hardcoded access keys into this client.
    settings = get_settings()
    region = (settings.aws_region or "").strip()
    if not region:
        raise EmailConfigurationError(
            "Missing required SES configuration when NOTIFICATION_EMAIL_MODE=ses: AWS_REGION"
        )
    return boto3.client("ses", region_name=region)


class SesEmailProvider(EmailProvider):
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
    ) -> str:
        settings = get_settings()
        validate_ses_settings(settings)

        sender = (from_email or "").strip()
        if not sender:
            raise EmailConfigurationError(
                "Missing required SES sender address for this email purpose"
            )

        source = _format_source(from_name if from_name is not None else settings.ses_from_name, sender)
        body: dict[str, dict[str, str]] = {
            "Text": {"Data": text_body, "Charset": "UTF-8"},
        }
        if html_body:
            body["Html"] = {"Data": html_body, "Charset": "UTF-8"}

        request: dict[str, object] = {
            "Source": source,
            "Destination": {"ToAddresses": [to_email]},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": body,
            },
        }
        if reply_to:
            request["ReplyToAddresses"] = [reply_to]

        try:
            response = _ses_client().send_email(**request)
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
