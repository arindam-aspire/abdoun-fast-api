"""Phone verification, OTP handling, and verified-mobile SMS rules."""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import RequestContext
from app.api.v1.routes import auth as auth_routes
from app.core.security import hash_secret, verify_secret
from app.models.live_schema import UserProfileChangeChallenge
from pydantic import ValidationError

from app.schemas.auth import (
    ConfirmSignUpRequest,
    ProfileUpdateVerifyRequest,
    SendPhoneOtpRequest,
    SignUpRequest,
    VerifyPhoneOtpRequest,
)
from app.services.auth import confirm_signup_user, register_signup_user, utc_now, verify_otp_challenge
from app.services.notifications import SmsEligibilityError, notify_registered_sms, send_registered_sms
from app.services.phone_verification import (
    PHONE_VERIFY_PURPOSE,
    PROFILE_PHONE_PURPOSE,
    apply_profile_phone_number,
    complete_profile_phone_verification,
    confirm_phone_otp,
    confirm_signup_phone_otp,
    issue_phone_verification_otp,
    prepare_signup_phone,
    request_phone_otp,
)
from tests.test_email_otp_responses import OTP_CODE, assert_no_otp_in_response

REGISTERED_PHONE = "+14155552671"
OTHER_PHONE = "+14155550199"
OTP = "246810"


def _user(**overrides) -> SimpleNamespace:
    data = {
        "id": uuid4(),
        "email": "user@example.com",
        "phone_number": REGISTERED_PHONE,
        "is_phone_verified": False,
        "is_email_verified": False,
        "is_active": False,
        "cognito_sub": None,
        "full_name": "Test User",
        "password_hash": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _challenge(
    *,
    otp: str = OTP,
    user_id=None,
    purpose: str = PHONE_VERIFY_PURPOSE,
    new_value: str = REGISTERED_PHONE,
    expires_at=None,
    consumed_at=None,
    attempt_count: int = 0,
    created_at=None,
) -> UserProfileChangeChallenge:
    return UserProfileChangeChallenge(
        id=uuid4(),
        user_id=user_id or uuid4(),
        purpose=purpose,
        new_value=new_value,
        otp_hash=hash_secret(otp),
        expires_at=expires_at or (utc_now() + timedelta(minutes=5)),
        created_at=created_at or utc_now(),
        attempt_count=attempt_count,
        consumed_at=consumed_at,
    )


def _db_with(challenge: UserProfileChangeChallenge | None) -> MagicMock:
    db = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = challenge
    return db


def _patch_issue_guards(monkeypatch, latest=None) -> None:
    monkeypatch.setattr("app.services.phone_verification._latest_otp_challenge", lambda *args, **kwargs: latest)
    monkeypatch.setattr("app.services.phone_verification._count_recent_otp_challenges", lambda *args, **kwargs: 0)
    monkeypatch.setattr("app.services.phone_verification._invalidate_open_challenges", lambda *args, **kwargs: None)


def test_signup_with_phone_stores_normalized_unverified_number(monkeypatch) -> None:
    existing = _user(is_phone_verified=True, is_email_verified=False, phone_number=None)
    cognito: dict[str, object] = {}
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda db, email: existing)
    monkeypatch.setattr(
        "app.services.phone_verification.prepare_signup_phone",
        lambda db, phone_number, exclude_user_id=None: REGISTERED_PHONE,
    )
    monkeypatch.setattr("app.services.auth.register_cognito_user", lambda **kwargs: cognito.update(kwargs) or "")
    monkeypatch.setattr("app.services.auth.assign_role", lambda *args, **kwargs: None)

    user = register_signup_user(
        MagicMock(),
        full_name="Test User",
        email="user@example.com",
        phone_number="14155552671",
        password="Password1!",
        role="owner",
    )

    assert user is existing
    assert user.phone_number == REGISTERED_PHONE
    assert user.is_phone_verified is False
    assert user.is_email_verified is False
    assert cognito["phone_number"] == REGISTERED_PHONE


def test_signup_without_phone_does_not_require_or_unverify_phone(monkeypatch) -> None:
    assert prepare_signup_phone(MagicMock(), None) is None
    assert prepare_signup_phone(MagicMock(), "  ") is None
    existing = _user(is_phone_verified=True, phone_number=REGISTERED_PHONE, is_email_verified=False)
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda db, email: existing)
    monkeypatch.setattr(
        "app.services.phone_verification.prepare_signup_phone",
        lambda db, phone_number, exclude_user_id=None: None,
    )
    monkeypatch.setattr("app.services.auth.register_cognito_user", lambda **kwargs: "")
    monkeypatch.setattr("app.services.auth.assign_role", lambda *args, **kwargs: None)

    user = register_signup_user(
        MagicMock(),
        full_name="Test User",
        email="user@example.com",
        phone_number=None,
        password="Password1!",
        role="owner",
    )

    assert user.phone_number == REGISTERED_PHONE
    assert user.is_phone_verified is True


def test_phone_otp_generation_is_hashed_and_not_returned(monkeypatch) -> None:
    _patch_issue_guards(monkeypatch)
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: OTP)
    sent: dict[str, str] = {}

    def capture_sms(*, to_phone: str, body: str) -> bool:
        sent["to_phone"] = to_phone
        sent["body"] = body
        return True

    monkeypatch.setattr("app.services.phone_verification.send_sms_notification", capture_sms)
    db = MagicMock()
    user = _user()

    result = issue_phone_verification_otp(
        db,
        user=user,
        phone=REGISTERED_PHONE,
        purpose=PHONE_VERIFY_PURPOSE,
        enforce_cooldown=True,
        require_delivery=True,
    )

    stored = db.add.call_args.args[0]
    assert result is None
    assert len(OTP) == 6 and OTP.isdigit()
    assert verify_secret(OTP, stored.otp_hash)
    assert stored.otp_hash != OTP
    assert sent["to_phone"] == REGISTERED_PHONE
    assert OTP in sent["body"]
    assert stored.attempt_count == 0
    assert stored.consumed_at is None


def test_phone_otp_confirmation_marks_only_phone_verified(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=False)
    monkeypatch.setattr(
        "app.services.phone_verification.resolve_phone_otp_subject",
        lambda *args, **kwargs: (user, REGISTERED_PHONE),
    )
    monkeypatch.setattr("app.services.phone_verification.verify_otp_challenge", lambda *args, **kwargs: _challenge())

    confirmed = confirm_phone_otp(
        MagicMock(),
        user_id=None,
        phone_number=REGISTERED_PHONE,
        phone_otp=OTP,
    )

    assert confirmed is user
    assert user.is_phone_verified is True
    assert user.is_email_verified is False


def test_invalid_otp_is_rejected_and_counted() -> None:
    challenge = _challenge()
    db = _db_with(challenge)

    with pytest.raises(HTTPException) as exc:
        verify_otp_challenge(db, purpose=PHONE_VERIFY_PURPOSE, code="000000", user=_user(id=challenge.user_id))

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid verification code"
    assert challenge.attempt_count == 1
    assert challenge.consumed_at is None


def test_expired_otp_is_rejected() -> None:
    challenge = _challenge(expires_at=utc_now() - timedelta(seconds=1))

    with pytest.raises(HTTPException) as exc:
        verify_otp_challenge(_db_with(challenge), purpose=PHONE_VERIFY_PURPOSE, code=OTP)

    assert exc.value.detail == "Verification code has expired"


def test_used_otp_is_rejected() -> None:
    challenge = _challenge(consumed_at=utc_now())

    with pytest.raises(HTTPException) as exc:
        verify_otp_challenge(_db_with(challenge), purpose=PHONE_VERIFY_PURPOSE, code=OTP)

    assert exc.value.detail == "Verification code has already been used"


def test_too_many_otp_attempts_are_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: MagicMock(auth_otp_max_attempts=2),
    )
    challenge = _challenge(attempt_count=2)

    with pytest.raises(HTTPException) as exc:
        verify_otp_challenge(_db_with(challenge), purpose=PHONE_VERIFY_PURPOSE, code=OTP)

    assert exc.value.status_code == 429
    assert exc.value.detail == "Too many verification attempts"
    assert challenge.consumed_at is None


def test_successful_otp_is_consumed() -> None:
    challenge = _challenge()

    verified = verify_otp_challenge(_db_with(challenge), purpose=PHONE_VERIFY_PURPOSE, code=OTP)

    assert verified is challenge
    assert challenge.consumed_at is not None


def test_resend_cooldown_blocks_a_second_phone_otp(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.phone_verification.get_settings",
        lambda: SimpleNamespace(auth_otp_resend_cooldown_seconds=60),
    )
    _patch_issue_guards(monkeypatch, latest=_challenge(created_at=utc_now()))
    send = MagicMock()
    monkeypatch.setattr("app.services.phone_verification.send_sms_notification", send)

    with pytest.raises(HTTPException) as exc:
        issue_phone_verification_otp(
            MagicMock(),
            user=_user(),
            phone=REGISTERED_PHONE,
            purpose=PHONE_VERIFY_PURPOSE,
            enforce_cooldown=True,
            require_delivery=True,
        )

    assert exc.value.status_code == 429
    assert exc.value.detail == "Please wait before requesting another verification code"
    send.assert_not_called()


def test_already_verified_phone_does_not_send_otp(monkeypatch) -> None:
    user = _user(is_phone_verified=True)
    monkeypatch.setattr("app.services.phone_verification.get_user_or_404", lambda db, user_id: user)
    issue = MagicMock()
    monkeypatch.setattr("app.services.phone_verification.issue_phone_verification_otp", issue)

    data, message = request_phone_otp(MagicMock(), user_id=user.id, phone_number=REGISTERED_PHONE)

    issue.assert_not_called()
    assert data == {"phone_verified": True}
    assert message == "Mobile number is already verified"
    assert OTP not in json.dumps(data)


def test_profile_phone_change_resets_verification_and_requires_a_new_otp(monkeypatch) -> None:
    user = _user(is_phone_verified=True, is_email_verified=True, phone_number=REGISTERED_PHONE)
    monkeypatch.setattr("app.services.phone_verification.assert_phone_available", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.phone_verification._invalidate_open_challenges", lambda *args, **kwargs: None)
    issued: dict[str, object] = {}
    monkeypatch.setattr(
        "app.services.phone_verification.issue_phone_verification_otp",
        lambda *args, **kwargs: issued.update(kwargs),
    )

    apply_profile_phone_number(MagicMock(), user=user, phone_number=OTHER_PHONE)

    assert user.phone_number == OTHER_PHONE
    assert user.is_phone_verified is False
    assert user.is_email_verified is True
    assert issued["phone"] == OTHER_PHONE
    assert issued["purpose"] == PHONE_VERIFY_PURPOSE


def test_verified_phone_can_receive_transactional_sms(monkeypatch) -> None:
    deliver = MagicMock(return_value=True)
    monkeypatch.setattr("app.services.notifications.sms.deliver_sms", deliver)
    user = _user(is_phone_verified=True)

    send_registered_sms(user=user, body="Listing update", requested_phone=REGISTERED_PHONE)

    deliver.assert_called_once_with(to_phone=REGISTERED_PHONE, body="Listing update")


@pytest.mark.parametrize("verified", [False, None])
def test_unverified_phone_cannot_receive_transactional_sms(monkeypatch, verified) -> None:
    deliver = MagicMock()
    monkeypatch.setattr("app.services.notifications.sms.deliver_sms", deliver)
    user = _user(is_phone_verified=verified)

    with pytest.raises(SmsEligibilityError) as exc:
        send_registered_sms(user=user, body="Listing update")

    assert exc.value.code == "phone_not_verified"
    deliver.assert_not_called()
    notify_registered_sms(user=user, body="Listing update")
    deliver.assert_not_called()


def test_missing_phone_cannot_receive_sms(monkeypatch) -> None:
    deliver = MagicMock()
    monkeypatch.setattr("app.services.notifications.sms.deliver_sms", deliver)

    with pytest.raises(SmsEligibilityError) as exc:
        send_registered_sms(user=_user(phone_number=None, is_phone_verified=True), body="Listing update")

    assert exc.value.code == "phone_missing"
    deliver.assert_not_called()


def test_transactional_sms_rejects_arbitrary_numbers(monkeypatch) -> None:
    deliver = MagicMock()
    monkeypatch.setattr("app.services.notifications.sms.deliver_sms", deliver)
    user = _user(is_phone_verified=True)

    with pytest.raises(SmsEligibilityError) as exc:
        send_registered_sms(user=user, body="Listing update", requested_phone=OTHER_PHONE)

    assert exc.value.code == "phone_not_registered"
    deliver.assert_not_called()


def test_authenticated_phone_otp_rejects_a_different_destination(monkeypatch) -> None:
    user = _user(is_phone_verified=False)
    monkeypatch.setattr("app.services.phone_verification.get_user_or_404", lambda db, user_id: user)
    issue = MagicMock()
    monkeypatch.setattr("app.services.phone_verification.issue_phone_verification_otp", issue)

    with pytest.raises(HTTPException) as exc:
        request_phone_otp(MagicMock(), user_id=user.id, phone_number=OTHER_PHONE)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Phone number does not match the registered mobile number"
    issue.assert_not_called()


def test_phone_otp_is_not_returned_in_api_responses(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_routes,
        "request_phone_otp",
        lambda *args, **kwargs: ({"phone_verified": False, "otp": OTP_CODE}, "Verification code sent."),
    )
    context = RequestContext(locale="en", user_id=uuid4())

    sent = auth_routes.send_phone_otp(SendPhoneOtpRequest(phone_number=REGISTERED_PHONE), context, MagicMock())
    resent = auth_routes.resend_phone_otp(SendPhoneOtpRequest(), context, MagicMock())

    assert sent["data"] == {"phone_verified": False}
    assert resent["data"] == {"phone_verified": False}
    assert_no_otp_in_response(sent)
    assert_no_otp_in_response(resent)

    user = _user(is_phone_verified=True)
    monkeypatch.setattr(auth_routes, "confirm_phone_otp", lambda *args, **kwargs: user)
    verified = auth_routes.verify_phone_otp(
        VerifyPhoneOtpRequest(phone_number=REGISTERED_PHONE, phone_otp=OTP_CODE),
        context,
        MagicMock(),
    )
    assert verified["data"] == {"verified": True, "phone_verified": True}
    assert_no_otp_in_response(verified)


def test_signup_response_with_phone_omits_otp(monkeypatch) -> None:
    user = _user(phone_number=REGISTERED_PHONE, is_phone_verified=False)
    sent: dict[str, object] = {}
    monkeypatch.setattr(auth_routes, "register_signup_user", lambda *args, **kwargs: user)
    monkeypatch.setattr(auth_routes, "create_otp_challenge", lambda *args, **kwargs: (_challenge(), OTP_CODE))
    monkeypatch.setattr(auth_routes, "send_dev_otp", lambda **kwargs: sent.update(kwargs))
    monkeypatch.setattr(auth_routes, "issue_signup_phone_otp", lambda *args, **kwargs: OTP_CODE)

    response = auth_routes.sign_up(
        SignUpRequest(
            full_name="Test User",
            email="user@example.com",
            phone_number=REGISTERED_PHONE,
            password="Password1!",
            role="owner",
        ),
        MagicMock(),
    )

    assert response["data"] == {"phone_verification_required": True}
    assert sent["skip_sms"] is True
    assert sent["purpose"] == "signup"
    assert_no_otp_in_response(response)


def test_phone_otp_is_not_logged(caplog, monkeypatch) -> None:
    _patch_issue_guards(monkeypatch)
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: OTP)
    monkeypatch.setattr("app.services.phone_verification.send_sms_notification", lambda **kwargs: True)

    with caplog.at_level("DEBUG"):
        issue_phone_verification_otp(
            MagicMock(),
            user=_user(),
            phone=REGISTERED_PHONE,
            purpose=PHONE_VERIFY_PURPOSE,
            enforce_cooldown=False,
            require_delivery=True,
        )

    assert OTP not in caplog.text
    assert REGISTERED_PHONE not in caplog.text


def _patch_signup_confirmation(monkeypatch, user, verify) -> None:
    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda db, username: user)
    monkeypatch.setattr("app.services.auth.CognitoService.enabled", property(lambda self: False))
    monkeypatch.setattr("app.services.auth.verify_otp_challenge", verify)
    monkeypatch.setattr("app.services.phone_verification.verify_otp_challenge", verify)
    monkeypatch.setattr("app.services.auth._open_challenge_matches", lambda *args, **kwargs: False)


def test_email_confirmation_without_mobile_code_leaves_phone_unverified(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=False)
    _patch_signup_confirmation(monkeypatch, user, lambda *args, **kwargs: _challenge())

    confirm_signup_user(MagicMock(), email=user.email, code=OTP)

    assert user.is_email_verified is True
    assert user.is_active is True
    assert user.is_phone_verified is False


def test_confirm_signup_without_phone_activates_on_email_code(monkeypatch) -> None:
    user = _user(phone_number=None, is_email_verified=False, is_phone_verified=False)
    _patch_signup_confirmation(monkeypatch, user, lambda *args, **kwargs: _challenge())

    confirm_signup_user(MagicMock(), email=user.email, code=OTP)

    assert user.is_email_verified is True
    assert user.is_active is True
    assert user.is_phone_verified is False


def test_confirm_signup_verifies_email_and_mobile_codes(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=False, is_active=False)
    seen: list[tuple[str, str]] = []

    def verify(db, *, purpose, code, user, new_value=None, **kwargs):
        seen.append((purpose, code))
        return _challenge(purpose=purpose)

    _patch_signup_confirmation(monkeypatch, user, verify)

    confirmed = confirm_signup_user(
        MagicMock(),
        email=user.email,
        code="111111",
        phone_otp="222222",
    )

    assert seen == [(PHONE_VERIFY_PURPOSE, "222222"), ("signup_confirm", "111111")]
    assert confirmed.is_email_verified is True
    assert confirmed.is_phone_verified is True
    assert confirmed.is_active is True


def test_confirm_signup_accepts_either_code_on_its_own(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=False, is_active=False)
    _patch_signup_confirmation(monkeypatch, user, lambda *args, **kwargs: _challenge())

    confirm_signup_user(MagicMock(), phone_number=REGISTERED_PHONE, phone_otp=OTP)
    assert user.is_phone_verified is True
    assert user.is_email_verified is False
    assert user.is_active is True

    confirm_signup_user(MagicMock(), email=user.email, code=OTP)
    assert user.is_email_verified is True
    assert user.is_active is True


def test_confirm_signup_accepts_mobile_otp_in_the_code_field(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=False, is_active=False)

    def matches(db, *, purpose, code, user, new_value=None) -> bool:
        return purpose == PHONE_VERIFY_PURPOSE and code == OTP

    _patch_signup_confirmation(monkeypatch, user, lambda *args, **kwargs: _challenge())
    monkeypatch.setattr("app.services.auth._open_challenge_matches", matches)

    confirm_signup_user(MagicMock(), email=user.email, code=OTP)

    assert user.is_phone_verified is True
    assert user.is_email_verified is False
    assert user.is_active is True


def test_password_login_succeeds_when_only_the_mobile_is_verified(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=True, is_active=False, password_hash="stored")
    calls: list[str] = []

    def login_password(**kwargs):
        calls.append("login")
        if calls.count("login") == 1:
            raise HTTPException(status_code=400, detail="Account is not confirmed")
        return {"AuthenticationResult": {}}

    monkeypatch.setattr("app.services.auth.find_user_by_username", lambda db, username: user)
    monkeypatch.setattr("app.services.auth.CognitoService.enabled", property(lambda self: True))
    monkeypatch.setattr("app.services.auth.cognito_service.login_password", login_password)
    monkeypatch.setattr("app.services.auth.cognito_service.admin_confirm_signup", lambda **kwargs: calls.append("confirm"))
    monkeypatch.setattr("app.services.auth.cognito_service.sub_from_auth_result", lambda result: "")
    monkeypatch.setattr("app.services.auth.cognito_service.get_user_sub", lambda **kwargs: "cognito-sub")
    monkeypatch.setattr("app.services.auth.load_user_roles", lambda db, user_id: [])
    monkeypatch.setattr("app.services.auth.ensure_agent_can_authenticate", lambda db, user: None)
    monkeypatch.setattr("app.services.auth.hash_secret", lambda password: "hashed")

    from app.services.auth import authenticate_password

    signed_in = authenticate_password(MagicMock(), username=user.email, password="Spring@2026")

    assert signed_in is user
    assert calls == ["login", "confirm", "login"]
    assert user.is_active is True
    assert user.is_phone_verified is True
    assert user.is_email_verified is False
    assert user.cognito_sub == "cognito-sub"


def test_confirm_signup_rejects_a_different_mobile_number(monkeypatch) -> None:
    user = _user()
    monkeypatch.setattr("app.services.phone_verification.verify_otp_challenge", lambda *args, **kwargs: _challenge())

    with pytest.raises(HTTPException) as exc:
        confirm_signup_phone_otp(
            MagicMock(),
            user=user,
            phone_number=OTHER_PHONE,
            phone_otp=OTP,
        )

    assert exc.value.status_code == 400
    assert user.is_phone_verified is False


def test_confirm_signup_request_accepts_email_or_mobile_code() -> None:
    both = ConfirmSignUpRequest(email="user@example.com", email_otp="111111", phone_otp="222222")
    assert both.code == "111111"
    assert both.phone_otp == "222222"
    mobile_only = ConfirmSignUpRequest(phone_number=REGISTERED_PHONE, phone_otp=OTP)
    assert mobile_only.phone_otp == OTP

    with pytest.raises(ValidationError):
        ConfirmSignUpRequest(email="user@example.com")


def test_confirm_signup_route_reports_both_channels(monkeypatch) -> None:
    user = _user(is_email_verified=True, is_phone_verified=True, is_active=True)
    captured: dict[str, object] = {}

    def confirm(db, **kwargs):
        captured.update(kwargs)
        return user

    monkeypatch.setattr(auth_routes, "confirm_signup_user", confirm)
    response = auth_routes.confirm_sign_up(
        ConfirmSignUpRequest(email="user@example.com", code="111111", phone_otp="222222"),
        MagicMock(),
    )

    assert captured["code"] == "111111"
    assert captured["phone_otp"] == "222222"
    assert response["data"] == {"verified": True, "email_verified": True, "phone_verified": True}
    assert response["message"] == "Account verified successfully"


def test_profile_email_verification_does_not_verify_phone(monkeypatch) -> None:
    user = _user(email="old@example.com", is_email_verified=False, is_phone_verified=False)
    monkeypatch.setattr(auth_routes, "get_user_or_404", lambda db, user_id: user)
    monkeypatch.setattr(auth_routes, "verify_otp_challenge", lambda *args, **kwargs: _challenge())

    auth_routes.verify_profile_update(
        ProfileUpdateVerifyRequest(email="new@example.com", email_otp=OTP),
        RequestContext(locale="en", user_id=user.id),
        MagicMock(),
    )

    assert user.email == "new@example.com"
    assert user.is_email_verified is True
    assert user.is_phone_verified is False


def test_profile_phone_verification_does_not_verify_email(monkeypatch) -> None:
    user = _user(is_email_verified=False, is_phone_verified=False, phone_number=None)
    monkeypatch.setattr("app.services.phone_verification.verify_otp_challenge", lambda *args, **kwargs: _challenge())
    monkeypatch.setattr("app.services.phone_verification.assert_phone_available", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.phone_verification._invalidate_open_challenges", lambda *args, **kwargs: None)

    complete_profile_phone_verification(
        MagicMock(),
        user=user,
        phone_number=REGISTERED_PHONE,
        phone_otp=OTP,
    )

    assert user.phone_number == REGISTERED_PHONE
    assert user.is_phone_verified is True
    assert user.is_email_verified is False


def test_profile_verify_accepts_saved_number_for_the_pending_mobile(monkeypatch) -> None:
    saved = "+919073494368111"
    pending = "+919073494368"
    user = _user(phone_number=saved, is_phone_verified=False, is_email_verified=True)
    challenge = _challenge(purpose=PROFILE_PHONE_PURPOSE, new_value=pending, user_id=user.id)

    def verify(db, *, purpose, code, user, new_value=None, challenge_id=None, **kwargs):
        if new_value == saved:
            raise HTTPException(status_code=400, detail="Verification code not found")
        assert purpose == PROFILE_PHONE_PURPOSE
        assert challenge_id == challenge.id
        assert code == OTP
        return challenge

    monkeypatch.setattr("app.services.phone_verification.verify_otp_challenge", verify)
    monkeypatch.setattr("app.services.phone_verification._latest_open_challenge", lambda *args, **kwargs: challenge)
    monkeypatch.setattr("app.services.phone_verification.assert_phone_available", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.phone_verification._invalidate_open_challenges", lambda *args, **kwargs: None)

    complete_profile_phone_verification(
        MagicMock(),
        user=user,
        phone_number=saved,
        phone_otp=OTP,
    )

    assert user.phone_number == pending
    assert user.is_phone_verified is True


def test_profile_verify_rejects_an_unrelated_mobile(monkeypatch) -> None:
    user = _user(phone_number=REGISTERED_PHONE, is_phone_verified=False)
    challenge = _challenge(purpose=PROFILE_PHONE_PURPOSE, new_value=REGISTERED_PHONE, user_id=user.id)

    def verify(db, *, purpose, code, user, new_value=None, challenge_id=None, **kwargs):
        raise HTTPException(status_code=400, detail="Verification code not found")

    monkeypatch.setattr("app.services.phone_verification.verify_otp_challenge", verify)
    monkeypatch.setattr("app.services.phone_verification._latest_open_challenge", lambda *args, **kwargs: challenge)

    with pytest.raises(HTTPException) as exc:
        complete_profile_phone_verification(
            MagicMock(),
            user=user,
            phone_number=OTHER_PHONE,
            phone_otp=OTP,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Verification code not found"
    assert user.phone_number == REGISTERED_PHONE
    assert user.is_phone_verified is False


def test_sns_failure_is_a_safe_error_and_does_not_log_the_otp(caplog, monkeypatch) -> None:
    _patch_issue_guards(monkeypatch)
    monkeypatch.setattr("app.services.auth.generate_otp", lambda: OTP)
    monkeypatch.setattr(
        "app.services.phone_verification.send_sms_notification",
        lambda **kwargs: False,
    )

    with caplog.at_level("WARNING"), pytest.raises(HTTPException) as exc:
        issue_phone_verification_otp(
            MagicMock(),
            user=_user(),
            phone=REGISTERED_PHONE,
            purpose=PHONE_VERIFY_PURPOSE,
            enforce_cooldown=False,
            require_delivery=True,
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "Unable to send verification code"
    assert OTP not in str(exc.value.detail)
    assert OTP not in caplog.text
    assert REGISTERED_PHONE not in caplog.text


def test_duplicate_phone_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.phone_verification.find_user_by_phone",
        lambda db, phone: _user(),
    )

    with pytest.raises(HTTPException) as exc:
        prepare_signup_phone(MagicMock(), REGISTERED_PHONE, exclude_user_id=uuid4())

    assert exc.value.status_code == 409
    assert exc.value.detail == "An account with this phone number already exists"


def test_invalid_phone_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        prepare_signup_phone(MagicMock(), "not-a-phone")

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid phone number"
