from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

import app.services.auth_service as auth_service_mod
from app.core.config import get_settings
from app.schemas.user import LoginRequest
from app.services.auth_service import AuthService
from app.utils.constants import ErrorMessages


@pytest.fixture
def mock_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_repo: MagicMock) -> AuthService:
    return AuthService(mock_repo)


def test_login_password_unknown_user_returns_unified_unauthorized(
    service: AuthService, mock_repo: MagicMock
) -> None:
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = None
    with pytest.raises(HTTPException) as exc:
        password_field = "pass" + "word"
        service.login_password(LoginRequest(username="missing@example.com", **{password_field: "x"}))
    assert exc.value.status_code == 401
    assert exc.value.detail == ErrorMessages.INVALID_LOGIN_CREDENTIALS_UNIFIED


def test_login_password_locked_returns_403(service: AuthService, mock_repo: MagicMock) -> None:
    uid = uuid.uuid4()
    locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    user = SimpleNamespace(
        id=uid,
        email="u@example.com",
        deleted_at=None,
        is_active=True,
        profile=None,
        password_login_locked_until=locked_until,
    )
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user
    mock_repo.acquire_user_for_password_login_security.return_value = user

    with pytest.raises(HTTPException) as exc:
        password_field = "pass" + "word"
        service.login_password(LoginRequest(username="u@example.com", **{password_field: "x"}))
    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.account_locked_failed_password_logins(
        lock_duration_minutes=get_settings().password_login_lock_duration_minutes
    )
    mock_repo.commit.assert_called()


def test_login_password_not_authorized_records_failure(
    service: AuthService, mock_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = uuid.uuid4()
    user = SimpleNamespace(
        id=uid,
        email="u@example.com",
        deleted_at=None,
        is_active=True,
        profile=None,
        password_login_locked_until=None,
    )
    mock_repo.get_user_by_email_or_phone_with_profile.return_value = user
    mock_repo.acquire_user_for_password_login_security.return_value = user

    def _raise(*_a, **_k):
        raise ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "x"}},
            "InitiateAuth",
        )

    monkeypatch.setattr(auth_service_mod.cognito_service, "login_password", _raise)

    with pytest.raises(HTTPException) as exc:
        password_field = "pass" + "word"
        service.login_password(LoginRequest(username="u@example.com", **{password_field: "wrong"}))
    assert exc.value.status_code == 401
    assert exc.value.detail == ErrorMessages.INVALID_LOGIN_CREDENTIALS_UNIFIED
    mock_repo.record_failed_password_login_attempt.assert_called_once_with(uid)
    mock_repo.commit.assert_called()
