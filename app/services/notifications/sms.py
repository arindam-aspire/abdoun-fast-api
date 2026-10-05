from __future__ import annotations

import logging
import re
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_E164_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")

# Required IAM permission for the runtime role/user when NOTIFICATION_SMS_MODE=sns:
# - sns:Publish


class SmsConfigurationError(Exception):
    """Raised when SNS configuration is incomplete."""


class SmsDeliveryError(Exception):
    """Raised when an SMS could not be delivered."""


def _country_calling_code() -> str:
    digits = re.sub(r"\D", "", get_settings().default_phone_country_calling_code or "")
    return digits.lstrip("0")


def mask_phone(phone_number: str | None) -> str:
    """Mask a phone number for logs. Keeps only the last four digits."""
    digits = re.sub(r"\D", "", phone_number or "")
    if len(digits) < 4:
        return "***"
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def phones_match(left: str | None, right: str | None) -> bool:
    normalized_left = to_e164_phone(left)
    normalized_right = to_e164_phone(right)
    return bool(normalized_left and normalized_right and normalized_left == normalized_right)


def to_e164_phone(phone_number: str | None) -> str | None:
    """Normalize a stored phone number to E.164 before SNS.

    Numbers that already include a country code are accepted with or without
    a leading plus. A local number that starts with 0 is prefixed with
    DEFAULT_PHONE_COUNTRY_CALLING_CODE.
    """
    if not phone_number:
        return None
    compact = re.sub(r"[\s\-()]", "", phone_number.strip())
    if not compact:
        return None
    calling_code = _country_calling_code()
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    elif calling_code and compact.startswith("0") and compact[1:].isdigit():
        compact = f"+{calling_code}{compact[1:]}"
    elif calling_code and compact.isdigit() and compact.startswith(calling_code):
        compact = f"+{compact}"
    elif compact.isdigit() and 8 <= len(compact) <= 15:
        compact = f"+{compact}"
    if _E164_PHONE.match(compact):
        return compact
    return None


@lru_cache
def _sns_client():
    # Use the default AWS credential chain (IAM role, instance profile, or env).
    # Never pass hardcoded access keys into this client.
    settings = get_settings()
    region = (settings.aws_region or "").strip().strip("\"'")
    if not region:
        raise SmsConfigurationError(
            "Missing required SNS configuration when NOTIFICATION_SMS_MODE=sns: AWS_REGION"
        )
    return boto3.client("sns", region_name=region)


def _sns_message_attributes() -> dict[str, dict[str, str]]:
    settings = get_settings()
    sms_type = (settings.sns_sms_type or "").strip() or "Transactional"
    attributes: dict[str, dict[str, str]] = {
        "AWS.SNS.SMS.SMSType": {
            "DataType": "String",
            "StringValue": sms_type,
        }
    }
    sender_id = (settings.sns_sender_id or "").strip()
    if sender_id:
        attributes["AWS.SNS.SMS.SenderID"] = {
            "DataType": "String",
            "StringValue": sender_id,
        }
    return attributes


def _publish_sns(*, phone_number: str, message: str) -> str:
    masked = mask_phone(phone_number)
    try:
        response = _sns_client().publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes=_sns_message_attributes(),
        )
    except SmsConfigurationError:
        raise
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "ClientError")
        logger.warning("sns_sms_send_failed to=%s error_code=%s", masked, error_code)
        raise SmsDeliveryError("Unable to send SMS notification") from exc
    except BotoCoreError as exc:
        logger.warning(
            "sns_sms_send_failed to=%s error_type=%s",
            masked,
            type(exc).__name__,
        )
        raise SmsDeliveryError("Unable to send SMS notification") from exc

    message_id = response.get("MessageId") or ""
    logger.info("sns_sms_sent to=%s message_id=%s", masked, message_id)
    return message_id


def deliver_sms(*, to_phone: str, body: str) -> bool:
    """Send one SMS. Failures are logged and never raised to the caller.

    Returns True when the message was handed to the configured provider
    (or recorded in log mode). Returns False when it was not sent.
    The message body is never written to logs.
    """
    settings = get_settings()
    mode = (settings.notification_sms_mode or "log").strip().lower()
    raw = (to_phone or "").strip()
    if not raw:
        logger.info("sms_notification_skipped reason=missing_phone")
        return False

    if mode == "log":
        logger.info("sms_notification_log_mode to=%s", mask_phone(raw))
        return True

    if mode != "sns":
        logger.warning("sms_notification_skipped mode=%s to=%s", mode, mask_phone(raw))
        return False

    phone = to_e164_phone(raw)
    if not phone:
        logger.warning("sms_notification_skipped reason=invalid_phone to=%s", mask_phone(raw))
        return False

    try:
        _publish_sns(phone_number=phone, message=body)
    except SmsConfigurationError:
        logger.warning("sms_notification_skipped reason=missing_aws_region")
        return False
    except SmsDeliveryError:
        return False
    except Exception:
        logger.warning("sms_notification_failed to=%s", mask_phone(phone))
        return False
    return True
