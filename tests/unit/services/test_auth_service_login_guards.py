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


def test_social_callback_401_when_email_or_sub_missing(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {"access_token": "a", "refresh_token": "r", "id_token": "i", "expires_in": 3600},
    )
    monkeypatch.setattr(auth_service_mod.cognito_service, "verify_token", lambda _t: {"sub": "sub123"})

    with pytest.raises(HTTPException) as exc:
        service.social_callback("code")
    assert exc.value.status_code == 401
    assert exc.value.detail == ErrorMessages.SOCIAL_AUTH_FAILED


def test_social_callback_blocks_soft_deleted_user(service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "exchange_code_for_tokens",
        lambda _code: {"access_token": "a", "refresh_token": "r", "id_token": "i", "expires_in": 3600},
    )
    monkeypatch.setattr(
        auth_service_mod.cognito_service,
        "verify_token",
        lambda _t: {"email": "u@example.com", "sub": "sub123", "email_verified": True, "phone_number_verified": False},
    )
    deleted_user = SimpleNamespace(
        is_active=True,
        deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cognito_sub="sub123",
        is_email_verified=False,
        is_phone_verified=False,
    )
    mock_repo.get_user_by_cognito_or_email_including_deleted.return_value = deleted_user

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
        lambda _t: {"email": "u@example.com", "sub": "sub123", "email_verified": True, "phone_number_verified": False},
    )
    inactive_user = SimpleNamespace(
        is_active=False,
        deleted_at=None,
        cognito_sub="sub123",
        is_email_verified=False,
        is_phone_verified=False,
    )
    mock_repo.get_user_by_cognito_or_email_including_deleted.return_value = inactive_user

    with pytest.raises(HTTPException) as exc:
        service.social_callback("code")
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.USER_INACTIVE

