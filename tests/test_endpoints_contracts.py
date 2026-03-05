"""
Smoke tests: verify app loads and public endpoints respond with expected structure.
No payload/response contract changes - only checks that routes exist and return expected shapes.
Run: pytest tests/test_endpoints_contracts.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    """GET /health - Docker health check."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"
    assert "service" in data


def test_list_properties_response_shape():
    """GET /api/v1/properties - response has data, total, page, pageSize."""
    r = client.get("/api/v1/properties?pageSize=2")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data
    assert isinstance(data["data"], list)


def test_properties_exclusive_response_shape():
    """GET /api/v1/properties/exclusive - same shape as list."""
    r = client.get("/api/v1/properties/exclusive?pageSize=2")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "total" in data


def test_cities_response_shape():
    """GET /api/v1/cities - returns data list and total."""
    r = client.get("/api/v1/cities")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "total" in data
    assert isinstance(data["data"], list)


def test_areas_response_shape():
    """GET /api/v1/areas - returns data list and total."""
    r = client.get("/api/v1/areas")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "total" in data


def test_geo_search_accepts_payload():
    """POST /api/v1/properties/geo-search - accepts bounds payload (no auth)."""
    r = client.post(
        "/api/v1/properties/geo-search",
        json={"mode": "bounds", "bounds": {"min_lng": 35.8, "min_lat": 31.9, "max_lng": 35.95, "max_lat": 32.0}, "limit": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_property_detail_404_for_invalid_id():
    """GET /api/v1/properties/{id} - 404 for non-existent."""
    r = client.get("/api/v1/properties/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_auth_signup_validation():
    """POST /api/v1/auth/signup - 422 or 400 for invalid payload (contract: accepts UserCreate)."""
    r = client.post("/api/v1/auth/signup", json={})
    assert r.status_code == 422  # validation error


def test_auth_me_requires_auth():
    """GET /api/v1/auth/me - 403 when no token."""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 403


def test_auth_logout_requires_auth():
    """POST /api/v1/auth/logout - 403 when no Bearer token (server must have token to invalidate session)."""
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 403
