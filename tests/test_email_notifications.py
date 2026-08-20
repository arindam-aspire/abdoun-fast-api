from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.services.auth import build_otp_response_data, send_dev_otp
from app.services.notifications import send_email_notification
from app.services.notifications.email.exceptions import EmailConfigurationError
from app.services.notifications.email.log_provider import LogEmailProvider
from app.services.notifications.email.service import get_email_provider
from app.services.notifications.email.ses_provider import SesEmailProvider, validate_ses_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    from app.services.notifications.email.ses_provider import _ses_client

    _ses_client.cache_clear()
    yield
    get_settings.cache_clear()
    _ses_client.cache_clear()


def _settings(**overrides: object) -> Settings:
    base = get_settings().model_dump()
    base.update(overrides)
    return Settings(**base)


def test_log_mode_does_not_call_ses(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.notifications.email.service.get_settings",
        lambda: _settings(notification_email_mode="log"),
    )
    provider = get_email_provider("log")
    assert isinstance(provider, LogEmailProvider)

    with patch("app.services.notifications.email.ses_provider._ses_client") as ses_client:
        message_id = send_email_notification(
            to_email="user@example.com",
            subject="Test subject",
            body="Plain text body",
        )

    assert message_id is None
    ses_client.assert_not_called()


def test_log_mode_preserves_logging_behavior(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.services.notifications.email.service.get_settings",
        lambda: _settings(notification_email_mode="log"),
    )

    with caplog.at_level("INFO"):
        send_email_notification(
            to_email="user@example.com",
            subject="Test subject",
            body="Plain text body",
        )

    assert "email_notification_log_mode" in caplog.text
    assert "user@example.com" in caplog.text
    assert "Test subject" in caplog.text


def test_ses_mode_sends_email_with_configured_sender(monkeypatch) -> None:
    configured_settings = _settings(
        notification_email_mode="ses",
        aws_region="eu-west-1",
        ses_from_email="no-reply@example.com",
        ses_from_name="Example App",
        email_otp_verification_subject="Verify your email address",
        app_name="Example App",
    )
    monkeypatch.setattr(
        "app.services.notifications.email.service.get_settings",
        lambda: configured_settings,
    )
    monkeypatch.setattr(
        "app.services.notifications.email.ses_provider.get_settings",
        lambda: configured_settings,
    )
    provider = get_email_provider("ses")
    assert isinstance(provider, SesEmailProvider)

    ses_client = MagicMock()
    ses_client.send_email.return_value = {"MessageId": "ses-message-id-123"}
    monkeypatch.setattr(
        "app.services.notifications.email.ses_provider._ses_client",
        lambda: ses_client,
    )

    message_id = send_email_notification(
        to_email="user@example.com",
        subject="Verify your email address",
        body="Your verification code is 123456",
        html_body="<p>Your verification code is <strong>123456</strong></p>",
    )

    assert message_id == "ses-message-id-123"
    ses_client.send_email.assert_called_once()
    kwargs = ses_client.send_email.call_args.kwargs
    assert kwargs["Source"] == "Example App <no-reply@example.com>"
    assert kwargs["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert kwargs["Message"]["Subject"]["Data"] == "Verify your email address"
    assert kwargs["Message"]["Body"]["Text"]["Data"] == "Your verification code is 123456"
    assert kwargs["Message"]["Body"]["Html"]["Data"] == "<p>Your verification code is <strong>123456</strong></p>"


def test_missing_ses_configuration_raises_clear_error() -> None:
    settings = _settings(
        notification_email_mode="ses",
        aws_region="",
        ses_from_email="",
    )

    with pytest.raises(EmailConfigurationError) as exc:
        validate_ses_settings(settings)

    assert "AWS_REGION" in str(exc.value)
    assert "SES_FROM_EMAIL" in str(exc.value)


def test_invalid_email_mode_raises_configuration_error() -> None:
    with pytest.raises(EmailConfigurationError) as exc:
        get_email_provider("invalid_value")

    assert "Unsupported NOTIFICATION_EMAIL_MODE" in str(exc.value)


def test_ses_failure_is_handled_without_exposing_secrets(monkeypatch, caplog) -> None:
    configured_settings = _settings(
        notification_email_mode="ses",
        aws_region="eu-west-1",
        ses_from_email="no-reply@example.com",
        ses_from_name="Example App",
    )
    monkeypatch.setattr(
        "app.services.notifications.email.service.get_settings",
        lambda: configured_settings,
    )
    monkeypatch.setattr(
        "app.services.notifications.email.ses_provider.get_settings",
        lambda: configured_settings,
    )

    ses_client = MagicMock()
    ses_client.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address is not verified."}},
        "SendEmail",
    )
    monkeypatch.setattr(
        "app.services.notifications.email.ses_provider._ses_client",
        lambda: ses_client,
    )

    with caplog.at_level("WARNING"):
        message_id = send_email_notification(
            to_email="user@example.com",
            subject="Verify your email address",
            body="Your verification code is 123456",
        )

    assert message_id is None
    assert "email_send_failed" in caplog.text
    assert "Unable to send email notification" in caplog.text
    assert "Email address is not verified" not in caplog.text


def test_expose_otp_in_response_false_hides_otp(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: _settings(expose_otp_in_response=False),
    )

    payload = build_otp_response_data(otp="123456", dev_email_otp="123456")

    assert "otp" not in payload
    assert "dev_email_otp" not in payload


def test_expose_otp_in_response_true_includes_otp(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: _settings(expose_otp_in_response=True),
    )

    payload = build_otp_response_data(otp="123456", dev_email_otp="123456")

    assert payload["otp"] == "123456"
    assert payload["dev_email_otp"] == "123456"


def test_send_dev_otp_uses_html_and_text_templates(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: _settings(
            notification_email_mode="log",
            app_name="Example App",
            auth_otp_ttl_seconds=600,
            email_otp_verification_subject="Verify your email address",
        ),
    )

    user = MagicMock()
    user.email = "user@example.com"
    user.phone_number = None
    challenge = MagicMock()
    challenge.expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)

    with patch("app.services.auth.send_email_notification") as send_email:
        send_dev_otp(user=user, purpose="signup", otp="123456", challenge=challenge)

    send_email.assert_called_once()
    kwargs = send_email.call_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert kwargs["subject"] == "Verify your email address"
    assert "123456" in kwargs["body"]
    assert "3 minutes" in kwargs["body"]
    assert "10 minutes" not in kwargs["body"]
    assert kwargs["html_body"] is not None
    assert "123456" in kwargs["html_body"]
    assert "Do not share this code with anyone." in kwargs["body"]
