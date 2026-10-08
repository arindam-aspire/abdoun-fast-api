from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.security import verify_secret
from app.services.auth import create_otp_challenge, resend_signup_confirmation
from app.services.notifications import send_sms_notification
from app.services.notifications.sms import _sns_client, to_e164_phone


@pytest.fixture(autouse=True)
def clear_sns_client_cache():
    get_settings.cache_clear()
    _sns_client.cache_clear()
    yield
    get_settings.cache_clear()
    _sns_client.cache_clear()


def test_to_e164_phone_uses_registered_international_number(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(update={"default_phone_country_calling_code": "962"}),
    )
    assert to_e164_phone("+962791199991") == "+962791199991"
    assert to_e164_phone("962791199991") == "+962791199991"
    assert to_e164_phone("0791199991") == "+962791199991"
    assert to_e164_phone("not-a-phone") is None
    assert to_e164_phone(None) is None


def test_local_numbers_use_configured_calling_code(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(update={"default_phone_country_calling_code": "44"}),
    )
    assert to_e164_phone("07123456789") == "+447123456789"
    assert to_e164_phone("447123456789") == "+447123456789"
    assert to_e164_phone("+14155552671") == "+14155552671"


def test_local_number_without_calling_code_is_not_guessed(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(update={"default_phone_country_calling_code": ""}),
    )
    assert to_e164_phone("0791199991") is None
    assert to_e164_phone("+962791199991") == "+962791199991"


def test_create_otp_challenge_stores_one_code(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: get_settings().model_copy(update={"auth_otp_ttl_seconds": 600}),
    )
    db = MagicMock()
    user = MagicMock()
    user.id = uuid4()

    challenge, otp = create_otp_challenge(db, user=user, purpose="login_otp", new_value="user@example.com")

    assert db.add.call_count == 1
    stored = db.add.call_args.args[0]
    assert stored is challenge
    assert verify_secret(otp, stored.otp_hash)
    assert len(otp) == 6


def test_resend_confirmation_sends_the_generated_otp_once(monkeypatch) -> None:
    user = MagicMock()
    user.email = "user@example.com"
    user.is_email_verified = False
    user.is_active = False
    challenge = MagicMock()
    sent: dict[str, object] = {}

    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda db, email: user)
    monkeypatch.setattr(
        "app.services.auth.CognitoService.enabled",
        property(lambda self: False),
    )
    monkeypatch.setattr(
        "app.services.auth.create_otp_challenge",
        lambda *args, **kwargs: (challenge, "111222"),
    )
    monkeypatch.setattr("app.services.auth.send_dev_otp", lambda **kwargs: sent.update(kwargs))

    result = resend_signup_confirmation(MagicMock(), email="user@example.com")

    assert result == "111222"
    assert sent["otp"] == "111222"
    assert sent["purpose"] == "signup"
    assert sent["skip_sms"] is True


def test_log_mode_does_not_write_otp(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(update={"notification_sms_mode": "log"}),
    )

    with caplog.at_level("INFO"):
        send_sms_notification(to_phone="+962791199991", body="Your verification code is 123456")

    assert "sms_notification_log_mode" in caplog.text
    assert "123456" not in caplog.text
    assert "verification code" not in caplog.text
    assert "+962791199991" not in caplog.text


def test_missing_phone_is_skipped(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(update={"notification_sms_mode": "sns"}),
    )

    with caplog.at_level("INFO"), patch("app.services.notifications.sms._sns_client") as client:
        send_sms_notification(to_phone="  ", body="Your verification code is 123456")

    client.assert_not_called()
    assert "missing_phone" in caplog.text
    assert "123456" not in caplog.text


def test_sns_publish_uses_region_without_inline_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(
            update={
                "notification_sms_mode": "sns",
                "aws_region": "us-west-2",
                "sns_sms_type": "Transactional",
                "sns_sender_id": None,
            }
        ),
    )
    sns = MagicMock()
    sns.publish.return_value = {"MessageId": "msg-1"}

    with patch("app.services.notifications.sms.boto3.client", return_value=sns) as boto_client:
        _sns_client.cache_clear()
        send_sms_notification(to_phone="+962791199991", body="Your verification code is 123456")

    boto_client.assert_called_once_with("sns", region_name="us-west-2")
    assert "aws_access_key_id" not in boto_client.call_args.kwargs
    assert "aws_secret_access_key" not in boto_client.call_args.kwargs
    sns.publish.assert_called_once()
    publish_kwargs = sns.publish.call_args.kwargs
    assert publish_kwargs["PhoneNumber"] == "+962791199991"
    assert publish_kwargs["Message"] == "Your verification code is 123456"
    assert publish_kwargs["MessageAttributes"]["AWS.SNS.SMS.SMSType"]["StringValue"] == "Transactional"


def test_sns_failure_does_not_raise_or_log_otp(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(
            update={
                "notification_sms_mode": "sns",
                "aws_region": "us-west-2",
                "sns_sms_type": "Transactional",
                "sns_sender_id": None,
            }
        ),
    )
    sns = MagicMock()
    sns.publish.side_effect = ClientError(
        {"Error": {"Code": "Throttling", "Message": "slow down 123456"}},
        "Publish",
    )

    with caplog.at_level("WARNING"), patch("app.services.notifications.sms._sns_client", return_value=sns):
        send_sms_notification(to_phone="0791199991", body="Your verification code is 123456")

    assert "sns_sms_send_failed" in caplog.text
    assert "Throttling" in caplog.text
    assert "123456" not in caplog.text
    assert "slow down" not in caplog.text
    assert "0791199991" not in caplog.text


def test_sns_botocore_failure_does_not_raise(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(
            update={
                "notification_sms_mode": "sns",
                "aws_region": "us-west-2",
                "sns_sms_type": "Transactional",
                "sns_sender_id": None,
            }
        ),
    )
    sns = MagicMock()
    sns.publish.side_effect = BotoCoreError()

    with caplog.at_level("WARNING"), patch("app.services.notifications.sms._sns_client", return_value=sns):
        send_sms_notification(to_phone="+962791199991", body="Your verification code is 123456")

    assert "BotoCoreError" in caplog.text
    assert "123456" not in caplog.text


def test_invalid_phone_skips_sns(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(
            update={
                "notification_sms_mode": "sns",
                "aws_region": "us-west-2",
                "sns_sms_type": "Transactional",
                "sns_sender_id": None,
            }
        ),
    )

    with caplog.at_level("WARNING"), patch("app.services.notifications.sms._sns_client") as client:
        send_sms_notification(to_phone="abc", body="Your verification code is 123456")

    client.assert_not_called()
    assert "invalid_phone" in caplog.text
    assert "123456" not in caplog.text


def test_missing_region_skips_sns(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.sms.get_settings",
        lambda: get_settings().model_copy(update={"notification_sms_mode": "sns", "aws_region": ""}),
    )

    with caplog.at_level("WARNING"), patch("app.services.notifications.sms.boto3.client") as boto_client:
        _sns_client.cache_clear()
        send_sms_notification(to_phone="+962791199991", body="Your verification code is 123456")

    boto_client.assert_not_called()
    assert "missing_aws_region" in caplog.text
    assert "123456" not in caplog.text
