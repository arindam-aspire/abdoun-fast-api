from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import app.core.auth as auth_mod


def test_get_current_user_401_when_token_verification_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_mod.cognito_service, "verify_token", lambda _t: None)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    db = MagicMock()  # treated as Session-like in the dependency

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert exc.value.status_code == 401


def test_get_current_user_401_when_token_use_is_not_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_mod.cognito_service, "verify_token", lambda _t: {"token_use": "id", "sub": "s"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert exc.value.status_code == 401


def test_get_current_user_401_when_sub_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_mod.cognito_service, "verify_token", lambda _t: {"token_use": "access"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert exc.value.status_code == 401


def test_get_current_user_fallback_to_email_when_sub_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_mod.cognito_service,
        "verify_token",
        lambda _t: {"token_use": "access", "sub": "sub123", "email": "user@example.com"},
    )

    active_user = SimpleNamespace(is_active=True, email="user@example.com")

    # First query (by sub) -> None, second query (by email) -> active_user
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = None
    second_result = MagicMock()
    second_result.scalar_one_or_none.return_value = active_user
    db = MagicMock()
    db.execute.side_effect = [first_result, second_result]

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    user = asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert user is active_user


def test_get_current_user_fallback_via_get_user_attributes_by_sub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers line 91: no email in payload; email from cognito_service.get_user_attributes_by_sub."""
    monkeypatch.setattr(
        auth_mod.cognito_service,
        "verify_token",
        lambda _t: {"token_use": "access", "sub": "sub123"},
    )
    monkeypatch.setattr(
        auth_mod.cognito_service,
        "get_user_attributes_by_sub",
        lambda _s: {"email": "from-cognito@example.com"},
    )

    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = None
    active_user = SimpleNamespace(is_active=True, email="from-cognito@example.com")
    second_result = MagicMock()
    second_result.scalar_one_or_none.return_value = active_user
    db = MagicMock()
    db.execute.side_effect = [first_result, second_result]

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    user = asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert user is active_user


def test_get_current_user_401_when_user_not_found_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_mod.cognito_service, "verify_token", lambda _t: {"token_use": "access", "sub": "sub123"}
    )
    monkeypatch.setattr(auth_mod.cognito_service, "get_user_attributes_by_sub", lambda _s: None)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute.return_value = result

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert exc.value.status_code == 401


def test_get_current_user_403_when_user_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_mod.cognito_service,
        "verify_token",
        lambda _t: {"token_use": "access", "sub": "sub123"},
    )

    inactive_user = SimpleNamespace(is_active=False, email="x@example.com")
    result = MagicMock()
    result.scalar_one_or_none.return_value = inactive_user
    db = MagicMock()
    db.execute.return_value = result

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_mod.get_current_user(credentials=creds, db=db))  # type: ignore[arg-type]
    assert exc.value.status_code == 403

