"""Unit tests for ProfileUpdateService (unified self-service profile)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.schemas.user import ProfileUpdateRequest, ProfileUpdateVerifyRequest
from app.services.profile_update_service import ProfileUpdateService, _hash_otp
from app.utils.constants import ErrorMessages, SuccessMessages


@pytest.fixture
def mock_auth_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_challenge_repo() -> MagicMock:
    return MagicMock()


def _user(
    *,
    email: str = "u@example.com",
    full_name: str = "User",
    phone: str | None = "+15555550100",
    cognito_sub: str | None = "sub-1",
) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = email
    u.full_name = full_name
    u.phone_number = phone
    u.cognito_sub = cognito_sub
    return u


def test_request_rejects_no_fields(mock_auth_repo: MagicMock, mock_challenge_repo: MagicMock) -> None:
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    body = ProfileUpdateRequest(full_name=None, email=None, phone_number=None)
    with pytest.raises(HTTPException) as exc:
        svc.request_profile_update(current_user=_user(), body=body)
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.PROFILE_UPDATE_NO_FIELDS


def test_request_rejects_no_effective_changes(
    mock_auth_repo: MagicMock, mock_challenge_repo: MagicMock,
) -> None:
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user()
    body = ProfileUpdateRequest(full_name=u.full_name, email=u.email, phone_number=u.phone_number)
    with pytest.raises(HTTPException) as exc:
        svc.request_profile_update(current_user=u, body=body)
    assert exc.value.detail == ErrorMessages.PROFILE_UPDATE_NO_CHANGES


@patch("app.services.profile_update_service.get_settings")
def test_request_name_only_immediate(
    mock_settings: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(profile_otp_hide_phone_code_in_response=False)
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(full_name="Old")
    body = ProfileUpdateRequest(full_name="New Name", email=None, phone_number=None)
    out = svc.request_profile_update(current_user=u, body=body)
    assert u.full_name == "New Name"
    mock_auth_repo.commit.assert_called_once()
    assert out.requires_verification is False
    assert out.verification_fields == []
    assert out.message == SuccessMessages.PROFILE_UPDATED_SUCCESS
    mock_challenge_repo.commit.assert_not_called()


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_request_email_creates_challenge_uses_cognito_custom_auth(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(
        profile_otp_pepper="pepper",
        profile_otp_ttl_minutes=10,
        profile_otp_hide_phone_code_in_response=False,
    )
    mock_cognito.login_otp_request.return_value = {"Session": "cognito-session-token"}
    mock_auth_repo.user_exists_by_email_excluding.return_value = False
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(email="old@example.com")
    body = ProfileUpdateRequest(email="new@example.com", full_name=None, phone_number=None)
    out = svc.request_profile_update(current_user=u, body=body)
    assert out.requires_verification is True
    assert out.verification_fields == ["email"]
    assert out.dev_phone_otp is None
    mock_cognito.login_otp_request.assert_called_once_with("old@example.com")
    cc_kwargs = mock_challenge_repo.create_challenge.call_args.kwargs
    assert cc_kwargs["cognito_custom_auth_session"] == "cognito-session-token"
    mock_challenge_repo.commit.assert_called_once()


@patch("app.services.profile_update_service.get_settings")
def test_request_phone_includes_dev_otp_by_default(
    mock_settings: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(
        profile_otp_pepper="pepper",
        profile_otp_ttl_minutes=10,
        profile_otp_hide_phone_code_in_response=False,
    )
    mock_auth_repo.user_exists_by_phone_excluding.return_value = False
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(phone="+15555550100")
    body = ProfileUpdateRequest(phone_number="+15555550199", full_name=None, email=None)
    out = svc.request_profile_update(current_user=u, body=body)
    assert out.requires_verification is True
    assert out.verification_fields == ["phone_number"]
    assert out.dev_phone_otp is not None
    assert len(out.dev_phone_otp) == 6
    mock_challenge_repo.commit.assert_called_once()


@patch("app.services.profile_update_service.get_settings")
def test_request_phone_hides_dev_otp_when_configured(
    mock_settings: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(
        profile_otp_pepper="pepper",
        profile_otp_ttl_minutes=10,
        profile_otp_hide_phone_code_in_response=True,
    )
    mock_auth_repo.user_exists_by_phone_excluding.return_value = False
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(phone="+15555550100")
    body = ProfileUpdateRequest(phone_number="+15555550199")
    out = svc.request_profile_update(current_user=u, body=body)
    assert out.requires_verification is True
    assert out.dev_phone_otp is None


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_request_email_and_phone_both_challenges(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(
        profile_otp_pepper="pepper",
        profile_otp_ttl_minutes=10,
        profile_otp_hide_phone_code_in_response=False,
    )
    mock_cognito.login_otp_request.return_value = {"Session": "sess"}
    mock_auth_repo.user_exists_by_email_excluding.return_value = False
    mock_auth_repo.user_exists_by_phone_excluding.return_value = False
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(email="a@b.com", phone="+100")
    body = ProfileUpdateRequest(email="z@b.com", phone_number="+19990000002")
    out = svc.request_profile_update(current_user=u, body=body)
    assert set(out.verification_fields) == {"email", "phone_number"}
    assert out.dev_phone_otp is not None
    assert mock_challenge_repo.create_challenge.call_count == 2


def test_verify_rejects_empty_body(mock_auth_repo: MagicMock, mock_challenge_repo: MagicMock) -> None:
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    body = ProfileUpdateVerifyRequest()
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(current_user=_user(), body=body)
    assert exc.value.detail == ErrorMessages.PROFILE_VERIFY_NO_PAIRS


def test_verify_email_without_otp(mock_auth_repo: MagicMock, mock_challenge_repo: MagicMock) -> None:
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    body = ProfileUpdateVerifyRequest(email="x@y.com", email_otp=None)
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(current_user=_user(), body=body)
    assert exc.value.detail == ErrorMessages.PROFILE_VERIFY_EMAIL_OTP_REQUIRED


def test_verify_phone_without_otp(mock_auth_repo: MagicMock, mock_challenge_repo: MagicMock) -> None:
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    body = ProfileUpdateVerifyRequest(phone_number="+19990000001", phone_otp=None)
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(current_user=_user(), body=body)
    assert exc.value.detail == ErrorMessages.PROFILE_VERIFY_PHONE_OTP_REQUIRED


def test_verify_otp_without_email(mock_auth_repo: MagicMock, mock_challenge_repo: MagicMock) -> None:
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    body = ProfileUpdateVerifyRequest(email=None, email_otp="123456")
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(current_user=_user(), body=body)
    assert exc.value.detail == ErrorMessages.PROFILE_VERIFY_EMAIL_REQUIRED


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_verify_email_invalid_otp(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(profile_otp_pepper="p", cognito_user_pool_id="")
    ch = MagicMock()
    ch.cognito_custom_auth_session = "sess"
    ch.otp_hash = "x"
    mock_challenge_repo.get_valid_challenge.return_value = ch
    mock_cognito.login_otp_verify.side_effect = ClientError(
        {"Error": {"Code": "NotAuthorizedException", "Message": "x"}},
        "RespondToAuthChallenge",
    )
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    body = ProfileUpdateVerifyRequest(email="new@example.com", email_otp="000000")
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(current_user=_user(), body=body)
    assert exc.value.detail == ErrorMessages.INVALID_OTP


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_verify_email_success(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(profile_otp_pepper="pepper", cognito_user_pool_id="pool")
    ch = MagicMock()
    ch.cognito_custom_auth_session = "sess"
    ch.otp_hash = "ignored"
    mock_challenge_repo.get_valid_challenge.return_value = ch
    mock_auth_repo.user_exists_by_email_excluding.return_value = False
    mock_cognito.login_otp_verify.return_value = {"AccessToken": "x"}
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(email="old@example.com")
    body = ProfileUpdateVerifyRequest(email="new@example.com", email_otp="111111")
    out = svc.verify_profile_update(current_user=u, body=body)
    assert u.email == "new@example.com"
    mock_cognito.login_otp_verify.assert_called_once_with("sess", "old@example.com", "111111")
    mock_challenge_repo.delete_challenge.assert_called_with(ch)
    mock_challenge_repo.commit.assert_called_once()
    assert out.message == SuccessMessages.PROFILE_UPDATED_SUCCESS


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_verify_duplicate_email_conflict(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(profile_otp_pepper="pepper", cognito_user_pool_id="")
    ch = MagicMock()
    ch.cognito_custom_auth_session = "sess"
    ch.otp_hash = "x"
    mock_challenge_repo.get_valid_challenge.return_value = ch
    mock_cognito.login_otp_verify.return_value = {"AccessToken": "t"}
    mock_auth_repo.user_exists_by_email_excluding.return_value = True
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(
            current_user=_user(),
            body=ProfileUpdateVerifyRequest(email="taken@example.com", email_otp="111111"),
        )
    assert exc.value.status_code == 409


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_verify_cognito_conflict_maps_to_409(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(profile_otp_pepper="pepper", cognito_user_pool_id="pool")
    ch = MagicMock()
    ch.cognito_custom_auth_session = "sess"
    ch.otp_hash = "x"
    mock_challenge_repo.get_valid_challenge.return_value = ch
    mock_auth_repo.user_exists_by_email_excluding.return_value = False
    mock_cognito.login_otp_verify.return_value = {"AccessToken": "t"}
    err = ClientError(
        {"Error": {"Code": "UsernameExistsException", "Message": "x"}},
        "AdminUpdateUserAttributes",
    )
    mock_cognito.admin_update_user_attributes.side_effect = err
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    with pytest.raises(HTTPException) as exc:
        svc.verify_profile_update(
            current_user=_user(),
            body=ProfileUpdateVerifyRequest(email="new@example.com", email_otp="111111"),
        )
    assert exc.value.status_code == 409


def test_admin_users_patch_still_has_user_create_permission() -> None:
    from pathlib import Path

    src = Path("app/api/v1/routes/users.py").read_text(encoding="utf-8")
    assert "require_permission(UserPermissions.USER_CREATE)" in src
    assert "@router.patch" in src


@patch("app.services.profile_update_service.cognito_service")
@patch("app.services.profile_update_service.get_settings")
def test_verify_phone_success(
    mock_settings: MagicMock,
    mock_cognito: MagicMock,
    mock_auth_repo: MagicMock,
    mock_challenge_repo: MagicMock,
) -> None:
    mock_settings.return_value = MagicMock(profile_otp_pepper="pepper", cognito_user_pool_id="pool")

    def _gc(*, user_id, purpose, new_value):
        if purpose == "phone":
            ch = MagicMock()
            ch.otp_hash = _hash_otp("222222", "pepper")
            return ch
        return None

    mock_challenge_repo.get_valid_challenge.side_effect = _gc
    mock_auth_repo.user_exists_by_phone_excluding.return_value = False
    svc = ProfileUpdateService(mock_auth_repo, mock_challenge_repo)
    u = _user(phone="+100")
    body = ProfileUpdateVerifyRequest(phone_number="+19990000003", phone_otp="222222")
    out = svc.verify_profile_update(current_user=u, body=body)
    assert u.phone_number == "+19990000003"
    assert out.message == SuccessMessages.PROFILE_UPDATED_SUCCESS
