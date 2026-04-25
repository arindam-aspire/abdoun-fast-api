"""
Smoke tests: verify app loads and endpoints respond with expected structure.
Step 2 (capture before behaviour) + Step 12 (router smoke tests) + Step 13 (API compatibility).
Run: pytest tests/test_endpoints_contracts.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api_contracts.expected_contracts import (
    EXPECTED_STATUS,
    LOCATION_RESPONSE_KEYS,
    PROPERTY_SEARCH_RESPONSE_KEYS,
)

client = TestClient(app)


# ---- Step 2: Successful cases ----
def test_health_returns_ok():
    """GET /health - Docker health check."""
    r = client.get("/health")
    assert r.status_code == EXPECTED_STATUS["health_ok"]
    data = r.json()
    assert data.get("status") == "healthy"
    assert "service" in data


def test_list_properties_response_shape(db_available):
    """GET /api/v1/properties - response has data, total, page, pageSize."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    r = client.get("/api/v1/properties?pageSize=2")
    assert r.status_code == EXPECTED_STATUS["properties_list_ok"]
    data = r.json()
    for key in PROPERTY_SEARCH_RESPONSE_KEYS:
        assert key in data, f"Missing key: {key}"
    assert isinstance(data["data"], list)


def test_properties_exclusive_response_shape(db_available):
    """GET /api/v1/properties/exclusive - same shape as list."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    r = client.get("/api/v1/properties/exclusive?pageSize=2")
    assert r.status_code == EXPECTED_STATUS["properties_exclusive_ok"]
    data = r.json()
    for key in PROPERTY_SEARCH_RESPONSE_KEYS:
        assert key in data


def test_cities_response_shape(db_available):
    """GET /api/v1/cities - returns data list and total."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    r = client.get("/api/v1/cities")
    assert r.status_code == EXPECTED_STATUS["cities_ok"]
    data = r.json()
    for key in LOCATION_RESPONSE_KEYS:
        assert key in data
    assert isinstance(data["data"], list)


def test_areas_response_shape(db_available):
    """GET /api/v1/areas - returns data list and total."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    r = client.get("/api/v1/areas")
    assert r.status_code == EXPECTED_STATUS["areas_ok"]
    data = r.json()
    for key in LOCATION_RESPONSE_KEYS:
        assert key in data


def test_geo_search_accepts_payload(db_available):
    """POST /api/v1/properties/geo-search - accepts bounds payload (no auth)."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    r = client.post(
        "/api/v1/properties/geo-search",
        json={
            "mode": "bounds",
            "bounds": {"min_lng": 35.8, "min_lat": 31.9, "max_lng": 35.95, "max_lat": 32.0},
            "limit": 5,
        },
    )
    assert r.status_code == EXPECTED_STATUS["geo_search_ok"]
    data = r.json()
    assert "items" in data
    assert "total" in data


# ---- Step 2: Typical validation / not found ----
def test_property_detail_404_for_invalid_id(db_available):
    """GET /api/v1/properties/{id} - 404 for non-existent."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    r = client.get("/api/v1/properties/00000000-0000-0000-0000-000000000000")
    assert r.status_code == EXPECTED_STATUS["property_detail_404"]


def test_auth_signup_validation():
    """POST /api/v1/auth/signup - 422 for invalid payload."""
    r = client.post("/api/v1/auth/signup", json={})
    assert r.status_code == EXPECTED_STATUS["auth_signup_validation_error"]


# ---- Step 2: Permission / auth failures ----
def test_auth_me_requires_auth():
    """GET /api/v1/auth/me - 403 when no token."""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == EXPECTED_STATUS["auth_me_unauthorized"]


def test_auth_me_profile_picture_requires_auth():
    """POST /api/v1/auth/me/profile-picture - 403 when no token."""
    r = client.post(
        "/api/v1/auth/me/profile-picture",
        json={"file_name": "a.png", "content_type": "image/png"},
    )
    assert r.status_code == EXPECTED_STATUS["auth_me_unauthorized"]


def test_auth_logout_requires_auth():
    """POST /api/v1/auth/logout - 403 when no Bearer token."""
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == EXPECTED_STATUS["auth_logout_unauthorized"]


def test_agents_list_requires_admin():
    """GET /api/v1/agents - 403 when not authenticated as admin (Step 12)."""
    r = client.get("/api/v1/agents")
    assert r.status_code == EXPECTED_STATUS["agents_list_unauthorized"]


def test_users_list_requires_auth():
    """GET /api/v1/users - 403 when not authenticated (Step 12)."""
    r = client.get("/api/v1/users")
    assert r.status_code == EXPECTED_STATUS["users_list_unauthorized"]


# ---- Step 13: API compatibility – paths and methods ----
def test_public_paths_respond(db_available):
    """Step 13: Public paths exist and respond with expected status."""
    paths = [
        ("/health", 200),
        ("/api/v1/cities", 200),
        ("/api/v1/areas", 200),
        ("/api/v1/properties", 200),
    ]
    for path, expected in paths:
        if not db_available and path != "/health":
            continue  # skip DB-dependent paths when PostgreSQL not running
        params = {"pageSize": 1} if "properties" in path else None
        r = client.get(path, params=params)
        assert r.status_code == expected, f"Path {path} returned {r.status_code}"
