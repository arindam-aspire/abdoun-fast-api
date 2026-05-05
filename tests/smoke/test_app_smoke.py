"""Smoke tests: app boots and core endpoints respond."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.utils.constants import ApiRoutes, SystemMessages


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == SystemMessages.HEALTHY
    assert body.get("service") == SystemMessages.SERVICE_NAME


def test_openapi_lists_v1_prefix() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json().get("paths") or {}
    assert any(p.startswith(f"{SystemMessages.API_V1_PREFIX}/") for p in paths)
