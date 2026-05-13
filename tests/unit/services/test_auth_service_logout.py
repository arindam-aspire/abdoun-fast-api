"""Logout: Cognito sign-out plus Remember Me session revocation and cookie clear."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials

import app.services.auth_service as auth_service_mod
from app.services.auth_service import AuthService


@pytest.fixture
def mock_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_remember_me_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_repo: MagicMock, mock_remember_me_repo: MagicMock) -> AuthService:
    return AuthService(mock_repo, remember_me_repository=mock_remember_me_repo)


def test_logout_revokes_remember_me_sessions_commits_and_clears_cookie(
    service: AuthService,
    mock_repo: MagicMock,
    mock_remember_me_repo: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service_mod.cognito_service, "logout", lambda _token: None)
    uid = uuid.uuid4()
    user = SimpleNamespace(id=uid, email="u@example.com")
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials="atoken")

    std, effect = service.logout(user, auth)

    mock_remember_me_repo.revoke_all_for_user.assert_called_once()
    call = mock_remember_me_repo.revoke_all_for_user.call_args
    assert call.args[0] == uid
    assert "revoked_at" in call.kwargs
    mock_repo.commit.assert_called_once()
    assert effect.clear_cookie is True
    assert std.success is True
    assert std.data is True


def test_logout_cognito_failure_still_revokes_remember_me_and_clears_cookie(
    service: AuthService,
    mock_repo: MagicMock,
    mock_remember_me_repo: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_token: str) -> None:
        raise RuntimeError("cognito down")

    monkeypatch.setattr(auth_service_mod.cognito_service, "logout", _boom)
    uid = uuid.uuid4()
    user = SimpleNamespace(id=uid, email="u@example.com")
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials="atoken")

    std, effect = service.logout(user, auth)

    mock_remember_me_repo.revoke_all_for_user.assert_called_once()
    mock_repo.commit.assert_called_once()
    assert effect.clear_cookie is True
    assert std.success is True
    assert std.data is False
