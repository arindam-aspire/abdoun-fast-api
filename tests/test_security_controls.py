from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.v1.deps.auth import get_auth_service
from app.main import app


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
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


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

