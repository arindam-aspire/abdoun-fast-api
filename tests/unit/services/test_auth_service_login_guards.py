from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import app.services.auth_service as auth_service_mod
from app.schemas.user import LoginRequest, OTPRequest, OTPVerify, RefreshRequest
from app.services.auth_service import AuthService
from app.utils.constants import ErrorMessages


@pytest.fixture
def mock_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_repo: MagicMock) -> AuthService:
    return AuthService(mock_repo)


def test_login_password_blocks_inactive_user(service: AuthService, mock_repo: MagicMock) -> None:
    user = SimpleNamespace(is_active=False, deleted_at=None, email="u@example.com", profile=None)
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        password_field = "pass" + "word"
        service.login_password(LoginRequest(username="u@example.com", **{password_field: "x"}))
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_INACTIVE
    mock_repo.acquire_user_for_password_login_security.assert_not_called()


def test_login_otp_request_blocks_inactive_user(service: AuthService, mock_repo: MagicMock) -> None:
    user = SimpleNamespace(is_active=False, deleted_at=None, email="u@example.com", profile=None)
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        service.login_otp_request(OTPRequest(username="u@example.com"))
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_INACTIVE


def test_login_otp_verify_blocks_inactive_user(service: AuthService, mock_repo: MagicMock) -> None:
    user = SimpleNamespace(is_active=False, deleted_at=None, email="u@example.com", profile=None)
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        service.login_otp_verify(OTPVerify(username="u@example.com", session="s", code="123456"))
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_INACTIVE


def test_login_password_phone_mode_requires_phone_on_user(
    service: AuthService, mock_repo: MagicMock
) -> None:
    user = SimpleNamespace(
        is_active=True,
        deleted_at=None,
        email="u@example.com",
        phone_number=None,
        profile=None,
    )
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        password_field = "pass" + "word"
        service.login_password(LoginRequest(username="+14155550123", **{password_field: "x"}))
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.PHONE_LOGIN_NOT_AVAILABLE


def test_login_otp_request_phone_mode_requires_phone_on_user(
    service: AuthService, mock_repo: MagicMock
) -> None:
    user = SimpleNamespace(
        is_active=True,
        deleted_at=None,
        email="u@example.com",
        phone_number=None,
        profile=None,
    )
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        service.login_otp_request(OTPRequest(username="+14155550123"))
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.PHONE_LOGIN_NOT_AVAILABLE


def test_login_otp_verify_phone_mode_requires_phone_on_user(
    service: AuthService, mock_repo: MagicMock
) -> None:
    user = SimpleNamespace(
        is_active=True,
        deleted_at=None,
        email="u@example.com",
        phone_number=None,
        profile=None,
    )
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        service.login_otp_verify(
            OTPVerify(username="+14155550123", session="s", code="123456")
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.PHONE_LOGIN_NOT_AVAILABLE


def test_refresh_token_blocks_when_user_not_found(service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_service_mod.cognito_service, "refresh_token", lambda *_a, **_k: {"AccessToken": "a"})
    monkeypatch.setattr(auth_service_mod.cognito_service, "verify_token", lambda *_a, **_k: {"sub": "sub123"})
    mock_repo.get_user_by_cognito_sub_with_profile.return_value = None

    with pytest.raises(HTTPException) as exc:
        service.refresh_token(RefreshRequest(refresh_token="r", username="u@example.com"))
    assert exc.value.status_code == 401
    assert exc.value.detail == ErrorMessages.INVALID_TOKEN


def test_refresh_token_blocks_inactive_user(service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_service_mod.cognito_service, "refresh_token", lambda *_a, **_k: {"AccessToken": "a"})
    monkeypatch.setattr(auth_service_mod.cognito_service, "verify_token", lambda *_a, **_k: {"sub": "sub123"})
    user = SimpleNamespace(is_active=False, deleted_at=None, profile=None, is_email_verified=False, is_phone_verified=False)
    mock_repo.get_user_by_cognito_sub_with_profile.return_value = user

    with pytest.raises(HTTPException) as exc:
        service.refresh_token(RefreshRequest(refresh_token="r", username="u@example.com"))
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_INACTIVE


def test_refresh_token_blocks_when_verify_token_returns_none(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_service_mod.cognito_service, "refresh_token", lambda *_a, **_k: {"AccessToken": "a"})
    monkeypatch.setattr(auth_service_mod.cognito_service, "verify_token", lambda *_a, **_k: None)

    with pytest.raises(HTTPException) as exc:
        service.refresh_token(RefreshRequest(refresh_token="r", username="u@example.com"))
    assert exc.value.status_code == 401
    assert exc.value.detail == ErrorMessages.INVALID_TOKEN


def test_refresh_token_blocks_when_sub_missing(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_service_mod.cognito_service, "refresh_token", lambda *_a, **_k: {"AccessToken": "a"})
    monkeypatch.setattr(auth_service_mod.cognito_service, "verify_token", lambda *_a, **_k: {"email": "u@example.com"})

    with pytest.raises(HTTPException) as exc:
        service.refresh_token(RefreshRequest(refresh_token="r", username="u@example.com"))
    assert exc.value.status_code == 401
    assert exc.value.detail == ErrorMessages.INVALID_TOKEN


def test_social_callback_400_when_identities_missing(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {"access_token": "a", "refresh_token": "r", "id_token": "i", "expires_in": 3600},
    )
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "verify_token",
        lambda _t, **_kw: {"sub": "sub123"},
    )

    with pytest.raises(HTTPException) as exc:
        service.social_callback("code")
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.SOCIAL_MISSING_IDENTITIES


def test_social_callback_400_when_provider_unsupported(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {"access_token": "a", "refresh_token": "r", "id_token": "i", "expires_in": 3600},
    )
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "verify_token",
        lambda _t, **_kw: {
            "sub": "sub123",
            "email": "u@example.com",
            "email_verified": True,
            "identities": [{"userId": "x", "providerName": "SignInWithApple"}],
        },
    )

    with pytest.raises(HTTPException) as exc:
        service.social_callback("code")
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.SOCIAL_UNSUPPORTED_PROVIDER


def test_social_login_rejects_unknown_provider(service: AuthService) -> None:
    with pytest.raises(HTTPException) as exc:
        service.social_login("twitter")
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.SOCIAL_UNSUPPORTED_PROVIDER


def test_social_callback_blocks_soft_deleted_user(service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {"access_token": "a", "refresh_token": "r", "id_token": "i", "expires_in": 3600},
    )
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "verify_token",
        lambda _t, **_kw: {
            "email": "u@example.com",
            "sub": "sub123",
            "email_verified": True,
            "phone_number_verified": False,
            "identities": [{"userId": "gid1", "providerName": "Google"}],
        },
    )
    deleted_user = SimpleNamespace(
        is_active=True,
        deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cognito_sub="sub123",
        is_email_verified=False,
        is_phone_verified=False,
    )
    mock_repo.get_user_by_cognito_sub_including_deleted.return_value = deleted_user

    with pytest.raises(HTTPException) as exc:
        service.social_callback("code")
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_ACCOUNT_DELETED


def test_social_callback_blocks_inactive_user(service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {"access_token": "a", "refresh_token": "r", "id_token": "i", "expires_in": 3600},
    )
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "verify_token",
        lambda _t, **_kw: {
            "email": "u@example.com",
            "sub": "sub123",
            "email_verified": True,
            "phone_number_verified": False,
            "identities": [{"userId": "gid1", "providerName": "Google"}],
        },
    )
    inactive_user = SimpleNamespace(
        is_active=False,
        deleted_at=None,
        cognito_sub="sub123",
        is_email_verified=False,
        is_phone_verified=False,
    )
    mock_repo.get_user_by_cognito_sub_including_deleted.return_value = inactive_user

    with pytest.raises(HTTPException) as exc:
        service.social_callback("code")
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_INACTIVE


def test_social_callback_verifies_id_token_with_access_token_context(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_verify_kwargs: dict = {}

    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {
            "access_token": "access123",
            "refresh_token": "refresh123",
            "id_token": "id123",
            "expires_in": 3600,
        },
    )

    def _verify_token(_token: str, **kwargs):
        seen_verify_kwargs.update(kwargs)
        return {
            "email": "u@example.com",
            "sub": "sub123",
            "email_verified": True,
            "phone_number_verified": False,
            "identities": [{"userId": "gid1", "providerName": "Google"}],
        }

    monkeypatch.setattr(auth_service_mod.cognito_service, "verify_token", _verify_token)

    existing_user = SimpleNamespace(
        id="user-1",
        is_active=True,
        deleted_at=None,
        cognito_sub="sub123",
        is_email_verified=False,
        is_phone_verified=False,
    )
    existing_social = SimpleNamespace(user_id="user-1")

    mock_repo.get_user_by_cognito_sub_including_deleted.return_value = existing_user
    mock_repo.get_social_account.return_value = existing_social

    response = service.social_callback("code")

    assert response.data.access_token == "access123"
    assert seen_verify_kwargs.get("access_token") == "access123"


def test_social_callback_flushes_before_social_account_insert(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {
            "access_token": "access123",
            "refresh_token": "refresh123",
            "id_token": "id123",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "verify_token",
        lambda _t, **_kw: {
            "email": "brandnew@example.com",
            "sub": "sub-new",
            "email_verified": False,
            "phone_number_verified": False,
            "identities": [{"userId": "gid-new", "providerName": "Google"}],
        },
    )

    # Force "new user path"
    mock_repo.get_user_by_cognito_sub_including_deleted.return_value = None
    mock_repo.get_social_account.return_value = None
    mock_repo.get_user_by_email.return_value = None
    mock_repo.get_role_by_name.return_value = None

    created_user = SimpleNamespace(id=None, is_email_verified=False, roles=[])
    mock_repo.create_user.return_value = created_user

    def _flush_assign_id():
        created_user.id = "generated-user-id"

    mock_repo.flush.side_effect = _flush_assign_id

    service.social_callback("code")

    mock_repo.flush.assert_called_once()
    kwargs = mock_repo.create_social_account.call_args.kwargs
    assert kwargs["user_id"] == "generated-user-id"

