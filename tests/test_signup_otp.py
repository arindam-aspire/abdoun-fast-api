"""Independent signup email and phone OTP generation and confirmation."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.api.v1.routes import auth as auth_routes
from app.core.security import hash_secret, verify_secret
from app.models.live_schema import UserProfileChangeChallenge
from app.schemas.auth import ConfirmSignUpRequest, ResendConfirmationRequest, SignUpRequest
from app.services.auth import (
    SIGNUP_EMAIL_PURPOSE,
    CognitoService,
    confirm_signup_user,
    resend_signup_confirmation,
    utc_now,
)
from app.services.phone_verification import PHONE_VERIFY_PURPOSE, issue_signup_phone_otp
from tests.test_email_otp_responses import assert_no_otp_in_response

EMAIL_OTP = "123456"
PHONE_OTP = "654321"
RESET_OTP = "111111"
PHONE = "+14155552671"


def _user(**overrides) -> SimpleNamespace:
    data = {
        "id": uuid4(),
        "email": "user@example.com",
        "phone_number": PHONE,
        "is_phone_verified": False,
        "is_email_verified": False,
        "is_active": False,
        "cognito_sub": None,
        "full_name": "Test User",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _challenge(
    *,
    otp: str,
    user_id: UUID,
    purpose: str,
    new_value: str,
    expires_at=None,
    consumed_at=None,
    attempt_count: int = 0,
) -> UserProfileChangeChallenge:
    return UserProfileChangeChallenge(
        id=uuid4(),
        user_id=user_id,
        purpose=purpose,
        new_value=new_value,
        otp_hash=hash_secret(otp),
        expires_at=expires_at or (utc_now() + timedelta(minutes=10)),
        created_at=utc_now(),
        attempt_count=attempt_count,
        consumed_at=consumed_at,
    )


class _Rows:
    def __init__(self, rows: list[UserProfileChangeChallenge]) -> None:
        self._rows = rows

    def all(self) -> list[UserProfileChangeChallenge]:
        return list(self._rows)

    def first(self) -> UserProfileChangeChallenge | None:
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows: list[UserProfileChangeChallenge]) -> None:
        self._rows = rows

    def scalars(self) -> _Rows:
        return _Rows(self._rows)


class ChallengeDb:
    """In-memory stand-in that honors purpose and user filters on OTP queries."""

    def __init__(self, rows: list[UserProfileChangeChallenge] | None = None) -> None:
        self.rows = list(rows or [])
        self.commits = 0

    def add(self, row: UserProfileChangeChallenge) -> None:
        self.rows.append(row)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def execute(self, stmt):  # noqa: ANN001
        params = {}
        try:
            params = dict(stmt.compile().params)
        except Exception:
            params = {}
        known_purposes = {SIGNUP_EMAIL_PURPOSE, PHONE_VERIFY_PURPOSE, "reset_password"}
        purposes: set[str] = set()
        for value in params.values():
            candidates = value if isinstance(value, (list, tuple)) else (value,)
            for item in candidates:
                if isinstance(item, str) and item in known_purposes:
                    purposes.add(item)
        user_ids = {value for value in params.values() if isinstance(value, UUID)}
        rows = self.rows
        if purposes:
            rows = [row for row in rows if row.purpose in purposes]
        if user_ids:
            rows = [row for row in rows if row.user_id in user_ids]
        return _Result(rows)


def _signup_pair(user, *, email_otp: str = EMAIL_OTP, phone_otp: str = PHONE_OTP, email_expires=None, phone_expires=None):
    email = _challenge(
        otp=email_otp,
        user_id=user.id,
        purpose=SIGNUP_EMAIL_PURPOSE,
        new_value=user.email,
        expires_at=email_expires,
    )
    phone = _challenge(
        otp=phone_otp,
        user_id=user.id,
        purpose=PHONE_VERIFY_PURPOSE,
        new_value=PHONE,
        expires_at=phone_expires,
    )
    return email, phone


def _confirm(monkeypatch, user, db: ChallengeDb, **kwargs):
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda _db, username: user)
    monkeypatch.setattr("app.services.auth.CognitoService.enabled", property(lambda self: False))
    return confirm_signup_user(db, email=kwargs.get("email", user.email), code=kwargs.get("code"), phone_number=kwargs.get("phone_number"), phone_otp=kwargs.get("phone_otp"))


def test_signup_generates_two_different_otps_and_sends_each_channel(monkeypatch) -> None:
    user = _user()
    db = ChallengeDb()
    generated = iter([EMAIL_OTP, EMAIL_OTP, PHONE_OTP])
    email_calls: list[dict[str, object]] = []
    sms_calls: list[dict[str, object]] = []

    monkeypatch.setattr("app.services.auth.generate_otp", lambda: next(generated))
    monkeypatch.setattr(auth_routes, "register_signup_user", lambda *args, **kwargs: user)
    monkeypatch.setattr("app.services.phone_verification._latest_otp_challenge", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.phone_verification._count_recent_otp_challenges", lambda *args, **kwargs: 0)
    monkeypatch.setattr("app.services.phone_verification._invalidate_open_challenges", lambda *args, **kwargs: None)

    email_result = SimpleNamespace(success=True, message_id="email-1")

    class _EmailService:
        def send_otp_verification(self, **kwargs):
            email_calls.append(kwargs)
            return email_result

        def send_password_reset(self, **kwargs):
            raise AssertionError("signup must not use the password-reset sender")

    monkeypatch.setattr("app.services.auth.get_email_service", lambda: _EmailService())
    monkeypatch.setattr(
        "app.services.phone_verification.send_sms_notification",
        lambda **kwargs: sms_calls.append(kwargs) or True,
    )

    response = auth_routes.sign_up(
        SignUpRequest(
            full_name="Test User",
            email=user.email,
            phone_number=PHONE,
            password="Password1!",
            role="owner",
        ),
        db,
    )

    email_rows = [row for row in db.rows if row.purpose == SIGNUP_EMAIL_PURPOSE]
    phone_rows = [row for row in db.rows if row.purpose == PHONE_VERIFY_PURPOSE]
    assert len(email_rows) == 1
    assert len(phone_rows) == 1
    assert verify_secret(EMAIL_OTP, email_rows[0].otp_hash)
    assert verify_secret(PHONE_OTP, phone_rows[0].otp_hash)
    assert not verify_secret(EMAIL_OTP, phone_rows[0].otp_hash)
    assert email_calls[0]["to_email"] == user.email
    assert email_calls[0]["otp"] == EMAIL_OTP
    assert PHONE in sms_calls[0]["to_phone"]
    assert PHONE_OTP in sms_calls[0]["body"]
    assert EMAIL_OTP not in sms_calls[0]["body"]
    assert_no_otp_in_response(response, secret=EMAIL_OTP)
    assert PHONE_OTP not in str(response)


def test_signup_email_failure_is_not_ignored(monkeypatch) -> None:
    user = _user()
    db = ChallengeDb()
    phone_issue = MagicMock()
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: EMAIL_OTP)
    monkeypatch.setattr(auth_routes, "register_signup_user", lambda *args, **kwargs: user)
    monkeypatch.setattr(auth_routes, "issue_signup_phone_otp", phone_issue)

    class _EmailService:
        def send_otp_verification(self, **kwargs):
            return SimpleNamespace(success=False, error="Unable to send email notification")

    monkeypatch.setattr("app.services.auth.get_email_service", lambda: _EmailService())

    with pytest.raises(HTTPException) as exc:
        auth_routes.sign_up(
            SignUpRequest(
                full_name="Test User",
                email=user.email,
                phone_number=PHONE,
                password="Password1!",
                role="owner",
            ),
            db,
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "Unable to send verification code"
    assert EMAIL_OTP not in str(exc.value.detail)
    phone_issue.assert_not_called()
    assert db.commits == 0


def test_email_otp_verifies_only_email(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])

    confirmed = _confirm(monkeypatch, user, db, code=EMAIL_OTP)

    assert confirmed.is_email_verified is True
    assert confirmed.is_phone_verified is False
    assert email.consumed_at is not None
    assert phone.consumed_at is None


def test_phone_otp_verifies_only_phone(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])

    confirmed = _confirm(monkeypatch, user, db, code=PHONE_OTP)

    assert confirmed.is_email_verified is False
    assert confirmed.is_phone_verified is True
    assert phone.consumed_at is not None
    assert email.consumed_at is None


def test_channels_verify_independently_in_either_order(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])
    _confirm(monkeypatch, user, db, code=EMAIL_OTP)
    confirmed = _confirm(monkeypatch, user, db, code=PHONE_OTP)
    assert confirmed.is_email_verified is True
    assert confirmed.is_phone_verified is True

    other = _user()
    other_email, other_phone = _signup_pair(other)
    other_db = ChallengeDb([other_email, other_phone])
    _confirm(monkeypatch, other, other_db, code=PHONE_OTP)
    assert other.is_phone_verified is True
    assert other.is_email_verified is False
    confirmed_other = _confirm(monkeypatch, other, other_db, code=EMAIL_OTP)
    assert confirmed_other.is_email_verified is True
    assert confirmed_other.is_phone_verified is True


def test_invalid_signup_otp_is_rejected(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])

    with pytest.raises(HTTPException) as exc:
        _confirm(monkeypatch, user, db, code="000000")

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid verification code"
    assert user.is_email_verified is False
    assert user.is_phone_verified is False
    assert email.consumed_at is None
    assert phone.consumed_at is None


def test_expired_email_otp_is_rejected(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user, email_expires=utc_now() - timedelta(seconds=1))
    db = ChallengeDb([email, phone])

    with pytest.raises(HTTPException) as exc:
        _confirm(monkeypatch, user, db, code=EMAIL_OTP)

    assert exc.value.detail == "Verification code has expired"
    assert user.is_email_verified is False
    assert user.is_phone_verified is False
    assert phone.consumed_at is None


def test_expired_phone_otp_is_rejected(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user, phone_expires=utc_now() - timedelta(seconds=1))
    db = ChallengeDb([email, phone])

    with pytest.raises(HTTPException) as exc:
        _confirm(monkeypatch, user, db, code=PHONE_OTP)

    assert exc.value.detail == "Verification code has expired"
    assert user.is_email_verified is False
    assert user.is_phone_verified is False
    assert email.consumed_at is None


def test_used_otp_cannot_be_reused(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])
    _confirm(monkeypatch, user, db, code=EMAIL_OTP)

    with pytest.raises(HTTPException) as exc:
        _confirm(monkeypatch, user, db, code=EMAIL_OTP)

    assert exc.value.detail == "Verification code has already been used"
    assert user.is_phone_verified is False
    assert phone.consumed_at is None


def test_password_reset_otp_does_not_verify_signup(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    reset = _challenge(
        otp=RESET_OTP,
        user_id=user.id,
        purpose="reset_password",
        new_value=user.email,
    )
    db = ChallengeDb([email, phone, reset])

    with pytest.raises(HTTPException) as exc:
        _confirm(monkeypatch, user, db, code=RESET_OTP)

    assert exc.value.detail == "Invalid verification code"
    assert user.is_email_verified is False
    assert user.is_phone_verified is False
    assert reset.consumed_at is None


def test_another_users_otp_does_not_verify_this_user(monkeypatch) -> None:
    user = _user()
    other = _user(email="other@example.com")
    foreign_email, foreign_phone = _signup_pair(other)
    db = ChallengeDb([foreign_email, foreign_phone])

    with pytest.raises(HTTPException) as exc:
        _confirm(monkeypatch, user, db, code=EMAIL_OTP)

    assert exc.value.detail == "Invalid verification code"
    assert user.is_email_verified is False
    assert user.is_phone_verified is False
    assert foreign_email.consumed_at is None
    assert foreign_phone.consumed_at is None


def test_resend_email_otp_leaves_phone_otp_in_place(monkeypatch) -> None:
    user = _user(is_active=False, is_email_verified=False)
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])
    sent: dict[str, object] = {}
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda _db, email: user)
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: "777777")
    monkeypatch.setattr("app.services.auth.send_dev_otp", lambda **kwargs: sent.update(kwargs) or True)

    resend_signup_confirmation(db, email=user.email)

    assert sent["skip_sms"] is True
    assert sent["otp"] == "777777"
    assert sent["purpose"] == "signup"
    assert phone.consumed_at is None
    assert email.consumed_at is not None
    assert any(row.purpose == SIGNUP_EMAIL_PURPOSE and row.consumed_at is None and verify_secret("777777", row.otp_hash) for row in db.rows)


def test_resend_phone_otp_leaves_email_otp_in_place(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda _db, email: user)
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: "888888")
    monkeypatch.setattr("app.services.phone_verification._latest_otp_challenge", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.phone_verification._count_recent_otp_challenges", lambda *args, **kwargs: 0)
    monkeypatch.setattr("app.services.phone_verification.send_sms_notification", lambda **kwargs: True)

    resend_signup_confirmation(db, email=user.email, channel="phone")

    assert email.consumed_at is None
    assert phone.consumed_at is not None
    assert any(row.purpose == PHONE_VERIFY_PURPOSE and row.consumed_at is None and verify_secret("888888", row.otp_hash) for row in db.rows)
    assert verify_secret(EMAIL_OTP, email.otp_hash)


def test_confirm_route_reports_the_channel_that_was_verified(monkeypatch) -> None:
    user = _user(is_email_verified=True, is_phone_verified=False, is_active=True)
    monkeypatch.setattr(auth_routes, "confirm_signup_user", lambda db, **kwargs: user)

    response = auth_routes.confirm_sign_up(
        ConfirmSignUpRequest(email=user.email, code=EMAIL_OTP),
        MagicMock(),
    )

    assert response["data"] == {"verified": True, "email_verified": True, "phone_verified": False}
    assert response["message"] == "Email verified. Mobile verification is still required"
    assert_no_otp_in_response(response, secret=EMAIL_OTP)


def test_cognito_confirmation_code_is_not_treated_as_the_email_otp(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda _db, username: user)
    monkeypatch.setattr("app.services.auth.CognitoService.enabled", property(lambda self: True))
    monkeypatch.setattr(
        "app.services.auth.cognito_service.confirm_signup",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("stored OTP must identify the channel")),
    )
    monkeypatch.setattr("app.services.auth.cognito_service.admin_confirm_signup", lambda **kwargs: None)
    monkeypatch.setattr("app.services.auth.cognito_service.get_user_sub", lambda **kwargs: "cognito-sub")

    confirmed = confirm_signup_user(db, email=user.email, code=EMAIL_OTP)

    assert confirmed.is_email_verified is True
    assert confirmed.is_phone_verified is False
    assert confirmed.cognito_sub == "cognito-sub"


def test_resend_confirmation_route_accepts_optional_channel(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def resend(db, *, email, channel=None):
        seen["email"] = email
        seen["channel"] = channel
        return None

    monkeypatch.setattr(auth_routes, "resend_signup_confirmation", resend)
    response = auth_routes.resend_confirmation(
        ResendConfirmationRequest(email="user@example.com", channel="phone"),
        MagicMock(),
    )
    assert seen == {"email": "user@example.com", "channel": "phone"}
    assert_no_otp_in_response(response)


def test_admin_confirm_signup_accepts_an_already_confirmed_cognito_user() -> None:
    service = CognitoService()
    service.user_pool_id = "pool"
    client = MagicMock()
    client.admin_confirm_sign_up.side_effect = ClientError(
        {
            "Error": {
                "Code": "NotAuthorizedException",
                "Message": "User cannot be confirmed. Current status is CONFIRMED",
            }
        },
        "AdminConfirmSignUp",
    )
    service.client = lambda: client

    service.admin_confirm_signup(email="user@example.com")

    client.admin_confirm_sign_up.assert_called_once()


def test_signup_phone_issue_does_not_consume_email_challenge(monkeypatch) -> None:
    user = _user()
    email, phone = _signup_pair(user)
    db = ChallengeDb([email, phone])
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: "999999")
    monkeypatch.setattr("app.services.phone_verification._latest_otp_challenge", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.phone_verification._count_recent_otp_challenges", lambda *args, **kwargs: 0)
    monkeypatch.setattr("app.services.phone_verification.send_sms_notification", lambda **kwargs: True)

    issue_signup_phone_otp(db, user=user, excluded_otps={EMAIL_OTP})

    assert email.consumed_at is None
    assert phone.consumed_at is not None
