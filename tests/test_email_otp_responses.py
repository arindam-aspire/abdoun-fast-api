"""Email OTP API responses must never include the OTP value or OTP fields."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.api.deps import RequestContext
from app.api.v1.routes import agency as agency_routes
from app.api.v1.routes import auth as auth_routes
from app.schemas.auth import (
    ForgotPasswordRequest,
    ProfileUpdateRequest,
    ResendConfirmationRequest,
    SignInWithOtpRequest,
    SignUpRequest,
)
from app.services.auth import build_otp_response_data, build_otp_response_meta, otp_delivery_message

OTP_CODE = "654321"
OTP_RESPONSE_KEYS = {"otp", "dev_email_otp", "dev_phone_otp"}


def assert_no_otp_in_response(payload: object, *, secret: str = OTP_CODE) -> None:
    serialized = json.dumps(payload)
    assert secret not in serialized

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                assert key not in OTP_RESPONSE_KEYS
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)


def test_build_otp_response_data_strips_nested_otp_fields() -> None:
    payload = build_otp_response_data(
        otp=OTP_CODE,
        dev_email_otp=OTP_CODE,
        dev_phone_otp=OTP_CODE,
        session="session-id",
        nested={"otp": OTP_CODE, "dev_email_otp": OTP_CODE, "keep": True},
    )

    assert payload == {"session": "session-id", "nested": {"keep": True}}
    assert_no_otp_in_response(payload)


def test_build_otp_response_meta_never_includes_otp() -> None:
    assert build_otp_response_meta(otp=OTP_CODE) == {}
    assert_no_otp_in_response(build_otp_response_meta(otp=OTP_CODE))


def test_otp_delivery_message_uses_sent_copy() -> None:
    assert (
        otp_delivery_message(
            fallback_dev_message="Verification code logged in dev mode",
            sent_message="If the account exists, a verification code has been sent",
        )
        == "If the account exists, a verification code has been sent"
    )


def _active_user() -> MagicMock:
    user = MagicMock()
    user.is_active = True
    user.email = "user@example.com"
    user.cognito_sub = None
    user.is_email_verified = False
    return user


def _challenge() -> MagicMock:
    challenge = MagicMock()
    challenge.id = uuid4()
    return challenge


def test_login_otp_request_email_response_omits_otp(monkeypatch) -> None:
    db = MagicMock()
    sent: dict[str, object] = {}
    monkeypatch.setattr(auth_routes, "find_user_by_username", lambda db, username: _active_user())
    monkeypatch.setattr(auth_routes, "ensure_agent_can_authenticate", lambda db, user: None)
    monkeypatch.setattr(
        auth_routes,
        "create_otp_challenge",
        lambda *args, **kwargs: (_challenge(), OTP_CODE),
    )

    def capture_send(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(auth_routes, "send_dev_otp", capture_send)

    response = auth_routes.login_with_otp_request(
        SignInWithOtpRequest(username="user@example.com"),
        db,
    )

    assert sent["otp"] == OTP_CODE
    assert sent["purpose"] == "login"
    assert "session" in response["data"]
    assert_no_otp_in_response(response)


def test_signup_response_omits_email_otp(monkeypatch) -> None:
    db = MagicMock()
    sent: dict[str, object] = {}
    monkeypatch.setattr(auth_routes, "register_signup_user", lambda *args, **kwargs: _active_user())
    monkeypatch.setattr(
        auth_routes,
        "create_otp_challenge",
        lambda *args, **kwargs: (_challenge(), OTP_CODE),
    )
    monkeypatch.setattr(auth_routes, "send_dev_otp", lambda **kwargs: sent.update(kwargs))

    response = auth_routes.sign_up(
        SignUpRequest(
            full_name="Test User",
            email="user@example.com",
            phone_number=None,
            password="Password1!",
            role="owner",
        ),
        db,
    )

    assert sent["otp"] == OTP_CODE
    assert response["data"] == {}
    assert_no_otp_in_response(response)


def test_resend_confirmation_response_omits_email_otp(monkeypatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(auth_routes, "resend_signup_confirmation", lambda db, email: OTP_CODE)

    response = auth_routes.resend_confirmation(
        ResendConfirmationRequest(email="user@example.com"),
        db,
    )

    assert response["data"] == {}
    assert_no_otp_in_response(response)


def test_profile_update_request_email_response_omits_otp(monkeypatch) -> None:
    db = MagicMock()
    sent: dict[str, object] = {}
    monkeypatch.setattr(auth_routes, "get_user_or_404", lambda db, user_id: _active_user())
    monkeypatch.setattr(
        auth_routes,
        "create_otp_challenge",
        lambda *args, **kwargs: (_challenge(), OTP_CODE),
    )
    monkeypatch.setattr(auth_routes, "send_dev_otp", lambda **kwargs: sent.update(kwargs))

    response = auth_routes.request_profile_update(
        ProfileUpdateRequest(email="new@example.com"),
        RequestContext(locale="en", user_id=uuid4()),
        db,
    )

    assert sent["otp"] == OTP_CODE
    assert response["data"]["requires_verification"] is True
    assert response["data"]["verification_fields"] == ["email"]
    assert_no_otp_in_response(response)


def test_forgot_password_request_response_omits_otp(monkeypatch) -> None:
    db = MagicMock()
    sent: dict[str, object] = {}
    user = _active_user()
    monkeypatch.setattr(auth_routes, "find_user_by_username", lambda db, username: user)
    monkeypatch.setattr(auth_routes, "cognito_service", SimpleNamespace(enabled=False))
    monkeypatch.setattr(
        auth_routes,
        "create_otp_challenge",
        lambda *args, **kwargs: (_challenge(), OTP_CODE),
    )
    monkeypatch.setattr(auth_routes, "send_dev_otp", lambda **kwargs: sent.update(kwargs))

    response = auth_routes.forgot_password(
        ForgotPasswordRequest(email="user@example.com"),
        db,
    )

    assert sent["otp"] == OTP_CODE
    assert sent["purpose"] == "password reset"
    assert response["data"] is True
    assert response["meta"] == {}
    assert_no_otp_in_response(response)


def test_agency_register_response_omits_email_otp(monkeypatch) -> None:
    db = MagicMock()
    sent: dict[str, object] = {}
    legal_document = SimpleNamespace(filename="license.pdf")
    monkeypatch.setattr(agency_routes, "validate_e164_phone", lambda value, field_name=None: "+962791199991")
    monkeypatch.setattr(agency_routes, "ensure_agency_contact_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(agency_routes, "create_user", lambda *args, **kwargs: _active_user())
    monkeypatch.setattr(
        agency_routes,
        "create_otp_challenge",
        lambda *args, **kwargs: (_challenge(), OTP_CODE),
    )
    monkeypatch.setattr(agency_routes, "send_dev_otp", lambda **kwargs: sent.update(kwargs))
    monkeypatch.setattr(agency_routes, "serialize_agency", lambda agency: {"id": str(agency.id)})
    monkeypatch.setattr(
        agency_routes,
        "get_settings",
        lambda: SimpleNamespace(default_currency="JOD", default_measurement_unit="sqm"),
    )

    response = asyncio.run(
        agency_routes.register_agency(
            db,
            agency_name="Test Agency",
            agency_trade_name="Test Trade",
            email="agency@example.com",
            phone_number="+962791199991",
            legal_document=legal_document,
        )
    )

    assert sent["otp"] == OTP_CODE
    assert "agency" in response["data"]
    assert_no_otp_in_response(response)
