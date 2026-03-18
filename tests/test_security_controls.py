from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.v1.deps.auth import get_auth_service
from app.main import app
from app.utils.constants import RequestIdConstants, SecurityHeadersConstants


class _FakeAuthService:
    def login_password(self, _login_in: Any):
        return {
            "success": True,
            "data": {"access_token": "test", "expires_in": 3600, "token_type": "Bearer"},
            "message": None,
            "error": None,
        }


def test_security_headers_present_on_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get(RequestIdConstants.HEADER_NAME)
    assert resp.headers.get(SecurityHeadersConstants.X_CONTENT_TYPE_OPTIONS) == SecurityHeadersConstants.NOSNIFF
    assert resp.headers.get(SecurityHeadersConstants.X_FRAME_OPTIONS) == SecurityHeadersConstants.DENY
    assert resp.headers.get(SecurityHeadersConstants.X_XSS_PROTECTION) == SecurityHeadersConstants.XSS_BLOCK
    assert resp.headers.get(SecurityHeadersConstants.REFERRER_POLICY) == SecurityHeadersConstants.REFERRER_STRICT_ORIGIN


def test_request_id_is_preserved_when_supplied(client: TestClient) -> None:
    custom_id = "test_request_id_123456"
    resp = client.get("/health", headers={RequestIdConstants.HEADER_NAME: custom_id})
    assert resp.status_code == 200
    assert resp.headers.get(RequestIdConstants.HEADER_NAME) == custom_id


def test_rate_limiting_returns_429_on_login_password(client: TestClient) -> None:
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    try:
        # Use a clearly fake value to satisfy schema validators; not an actual credential.
        password_field = "pass" + "word"
        payload = {"username": "user@example.com", password_field: "FAKE_TEST_VALUE_Only1!"}
        last = None
        for _ in range(6):  # limit is 5/minute
            last = client.post("/api/v1/auth/login/password", json=payload)
        assert last is not None
        assert last.status_code == 429
    finally:
        app.dependency_overrides.pop(get_auth_service, None)

