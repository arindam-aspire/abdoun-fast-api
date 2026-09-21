from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings
from app.services.auth import build_otp_response_data, send_dev_otp
from app.services.notifications import EmailPurpose, EmailService, get_email_service, send_email_notification
from app.services.notifications.email.exceptions import EmailConfigurationError
from app.services.notifications.email.log_provider import LogEmailProvider
from app.services.notifications.email.purpose import resolve_sender_email, validate_ses_settings
from app.services.notifications.email.service import get_email_provider
from app.services.notifications.email.ses_provider import SesEmailProvider


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


def _ses_settings(**overrides: object) -> Settings:
    values: dict[str, object] = dict(
        notification_email_mode="ses",
        aws_region="eu-west-1",
        ses_from_name="Abdoun Real Estate",
        ses_support_email="support@example.com",
        ses_no_reply_email="no-reply@example.com",
        ses_info_email="info@example.com",
        app_name="Abdoun Real Estate",
        email_otp_verification_subject="Verify your email address",
    )
    values.update(overrides)
    return _settings(**values)


def _patch_settings(monkeypatch, settings: Settings) -> None:
    monkeypatch.setattr("app.services.notifications.email.service.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.notifications.email.ses_provider.get_settings", lambda: settings)


def _mock_ses_client(monkeypatch, *, message_id: str = "ses-message-id-123") -> MagicMock:
    ses_client = MagicMock()
    ses_client.send_email.return_value = {"MessageId": message_id}
    monkeypatch.setattr(
        "app.services.notifications.email.ses_provider._ses_client",
        lambda: ses_client,
    )
    return ses_client


def test_log_mode_does_not_call_ses(monkeypatch) -> None:
    _patch_settings(monkeypatch, _settings(notification_email_mode="log"))
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
    _patch_settings(monkeypatch, _settings(notification_email_mode="log"))

    with caplog.at_level("INFO"):
        send_email_notification(
            to_email="user@example.com",
            subject="Test subject",
            body="Plain text body",
        )

    assert "email_notification_log_mode" in caplog.text
    assert "user@example.com" in caplog.text
    assert "Test subject" in caplog.text
    assert "Plain text body" not in caplog.text


def test_ses_mode_sends_email_with_configured_sender(monkeypatch) -> None:
    configured_settings = _ses_settings()
    _patch_settings(monkeypatch, configured_settings)
    provider = get_email_provider("ses")
    assert isinstance(provider, SesEmailProvider)

    ses_client = _mock_ses_client(monkeypatch)

    message_id = send_email_notification(
        to_email="user@example.com",
        subject="Verify your email address",
        body="Your verification code is 123456",
        html_body="<p>Your verification code is <strong>123456</strong></p>",
        purpose=EmailPurpose.OTP_VERIFICATION,
    )

    assert message_id == "ses-message-id-123"
    ses_client.send_email.assert_called_once()
    kwargs = ses_client.send_email.call_args.kwargs
    assert kwargs["Source"] == "Abdoun Real Estate <no-reply@example.com>"
    assert kwargs["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert kwargs["ReplyToAddresses"] == ["support@example.com"]
    assert kwargs["Message"]["Subject"]["Data"] == "Verify your email address"
    assert kwargs["Message"]["Body"]["Text"]["Data"] == "Your verification code is 123456"
    assert kwargs["Message"]["Body"]["Html"]["Data"] == "<p>Your verification code is <strong>123456</strong></p>"


@pytest.mark.parametrize(
    ("purpose", "expected_sender"),
    [
        (EmailPurpose.OTP_VERIFICATION, "no-reply@example.com"),
        (EmailPurpose.PASSWORD_RESET, "no-reply@example.com"),
        (EmailPurpose.AGENT_INVITATION, "info@example.com"),
        (EmailPurpose.ACCOUNT_NOTIFICATION, "support@example.com"),
        (EmailPurpose.GENERAL, "no-reply@example.com"),
    ],
)
def test_email_service_uses_purpose_specific_sender(monkeypatch, purpose, expected_sender) -> None:
    _patch_settings(monkeypatch, _ses_settings())
    ses_client = _mock_ses_client(monkeypatch)

    result = EmailService().send(
        to_email="user@example.com",
        subject="Purpose routing",
        text_body="Hello",
        purpose=purpose,
    )

    assert result.success is True
    assert result.message_id == "ses-message-id-123"
    assert result.purpose == purpose.value
    source = ses_client.send_email.call_args.kwargs["Source"]
    assert source == f"Abdoun Real Estate <{expected_sender}>"


def test_email_service_methods_return_structured_result(monkeypatch) -> None:
    _patch_settings(monkeypatch, _ses_settings())
    ses_client = _mock_ses_client(monkeypatch, message_id="invite-1")
    service = get_email_service()

    result = service.send_agent_invitation(
        to_email="agent@example.com",
        subject="Abdoun agent invitation",
        text_body="Complete onboarding using this link: https://example.com/invite",
    )

    assert result.success is True
    assert result.message_id == "invite-1"
    assert result.error is None
    kwargs = ses_client.send_email.call_args.kwargs
    assert kwargs["Source"] == "Abdoun Real Estate <info@example.com>"
    assert "Html" in kwargs["Message"]["Body"]
    assert "Text" in kwargs["Message"]["Body"]


def test_missing_ses_configuration_raises_clear_error() -> None:
    settings = _settings(
        notification_email_mode="ses",
        aws_region="",
        ses_from_email="",
        ses_support_email="",
        ses_no_reply_email="",
        ses_info_email="",
    )

    with pytest.raises(EmailConfigurationError) as exc:
        validate_ses_settings(settings)

    assert "AWS_REGION" in str(exc.value)
    assert "SES_NO_REPLY_EMAIL" in str(exc.value)
    assert "SES_SUPPORT_EMAIL" in str(exc.value)
    assert "SES_INFO_EMAIL" in str(exc.value)


def test_missing_purpose_sender_raises_clear_error() -> None:
    settings = _settings(
        notification_email_mode="ses",
        aws_region="eu-west-1",
        ses_from_email="",
        ses_no_reply_email="",
        ses_support_email="support@example.com",
        ses_info_email="info@example.com",
    )

    with pytest.raises(EmailConfigurationError) as exc:
        resolve_sender_email(settings, EmailPurpose.OTP_VERIFICATION)

    assert "SES_NO_REPLY_EMAIL" in str(exc.value)


def test_invalid_email_mode_raises_configuration_error() -> None:
    with pytest.raises(EmailConfigurationError) as exc:
        get_email_provider("invalid_value")

    assert "Unsupported NOTIFICATION_EMAIL_MODE" in str(exc.value)


def test_ses_failure_is_handled_without_exposing_secrets(monkeypatch, caplog) -> None:
    _patch_settings(monkeypatch, _ses_settings())

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
        result = EmailService().send_otp_verification(
            to_email="user@example.com",
            otp="123456",
            expiry_minutes=3,
        )

    assert result.success is False
    assert result.message_id is None
    assert result.error == "Unable to send email notification"
    assert "email_send_failed" in caplog.text
    assert "Unable to send email notification" in caplog.text
    assert "Email address is not verified" not in caplog.text
    assert "123456" not in caplog.text


def test_ses_botocore_error_returns_failure(monkeypatch, caplog) -> None:
    _patch_settings(monkeypatch, _ses_settings())
    ses_client = MagicMock()
    ses_client.send_email.side_effect = BotoCoreError()
    monkeypatch.setattr(
        "app.services.notifications.email.ses_provider._ses_client",
        lambda: ses_client,
    )

    with caplog.at_level("WARNING"):
        result = EmailService().send_general(
            to_email="user@example.com",
            subject="System notice",
            text_body="A system update is available.",
        )

    assert result.success is False
    assert result.error == "Unable to send email notification"
    assert "BotoCoreError" in caplog.text
    assert "A system update is available." not in caplog.text


def test_ses_client_uses_region_without_inline_credentials(monkeypatch) -> None:
    configured_settings = _ses_settings()
    _patch_settings(monkeypatch, configured_settings)
    from app.services.notifications.email.ses_provider import _ses_client

    _ses_client.cache_clear()
    with patch("app.services.notifications.email.ses_provider.boto3.client") as boto_client:
        boto_client.return_value = MagicMock()
        _ses_client()

    boto_client.assert_called_once_with("ses", region_name="eu-west-1")
    assert "aws_access_key_id" not in boto_client.call_args.kwargs
    assert "aws_secret_access_key" not in boto_client.call_args.kwargs


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

    with patch("app.services.auth.get_email_service") as get_service:
        service = MagicMock()
        get_service.return_value = service
        send_dev_otp(user=user, purpose="signup", otp="123456", challenge=challenge)

    service.send_otp_verification.assert_called_once()
    kwargs = service.send_otp_verification.call_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert kwargs["otp"] == "123456"
    assert kwargs["expiry_minutes"] == 3
    assert kwargs["subject"] == "Verify your email address"
    service.send_password_reset.assert_not_called()


def test_send_dev_otp_password_reset_uses_password_sender(monkeypatch) -> None:
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

    with patch("app.services.auth.get_email_service") as get_service:
        service = MagicMock()
        get_service.return_value = service
        send_dev_otp(user=user, purpose="password reset", otp="654321", challenge=None)

    service.send_password_reset.assert_called_once()
    kwargs = service.send_password_reset.call_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert kwargs["otp"] == "654321"
    service.send_otp_verification.assert_not_called()


def test_send_dev_otp_login_email_skips_sms(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: _settings(
            notification_email_mode="ses",
            app_name="Example App",
            auth_otp_ttl_seconds=600,
            email_otp_verification_subject="Verify your email address",
        ),
    )

    user = MagicMock()
    user.email = "superadmin@yopmail.com"
    user.phone_number = "+962791199991"

    with (
        patch("app.services.auth.get_email_service") as get_service,
        patch("app.services.auth.send_sms_notification") as send_sms,
    ):
        service = MagicMock()
        get_service.return_value = service
        send_dev_otp(
            user=user,
            purpose="login",
            otp="123456",
            identifier="superadmin@yopmail.com",
        )

    service.send_otp_verification.assert_called_once()
    send_sms.assert_not_called()


def test_send_dev_otp_login_phone_skips_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: _settings(
            notification_email_mode="ses",
            app_name="Example App",
            auth_otp_ttl_seconds=600,
            email_otp_verification_subject="Verify your email address",
        ),
    )

    user = MagicMock()
    user.email = "superadmin@yopmail.com"
    user.phone_number = "+962791199991"

    with (
        patch("app.services.auth.get_email_service") as get_service,
        patch("app.services.auth.send_sms_notification") as send_sms,
    ):
        service = MagicMock()
        get_service.return_value = service
        send_dev_otp(
            user=user,
            purpose="login",
            otp="123456",
            identifier="+962791199991",
        )

    service.send_otp_verification.assert_not_called()
    service.send_password_reset.assert_not_called()
    send_sms.assert_called_once()


def test_email_service_generates_html_when_missing(monkeypatch) -> None:
    _patch_settings(monkeypatch, _ses_settings())
    ses_client = _mock_ses_client(monkeypatch)

    EmailService().send_account_notification(
        to_email="owner@example.com",
        subject="Your Abdoun owner account was deactivated",
        text_body="Your owner account has been deactivated.",
    )

    html_body = ses_client.send_email.call_args.kwargs["Message"]["Body"]["Html"]["Data"]
    assert "<html>" in html_body
    assert "Your owner account has been deactivated." in html_body
    assert ses_client.send_email.call_args.kwargs["Source"] == "Abdoun Real Estate <support@example.com>"
