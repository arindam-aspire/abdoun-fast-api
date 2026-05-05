"""
Expected API contracts (Step 2 – before behaviour).
Used by router smoke tests (Step 12) and validation (Step 13) to ensure
paths, methods, status codes, and response shapes remain unchanged.
"""
# Paths and methods that must remain unchanged (Step 13)
API_PATHS = [
    ("GET", "/health"),
    ("GET", "/api/v1/location-taxonomy"),
    ("GET", "/api/v1/properties"),
    ("GET", "/api/v1/properties/exclusive"),
    ("POST", "/api/v1/properties/geo-search"),
    ("GET", "/api/v1/auth/signup"),  # 405 or 422 - method not GET, but path exists
    ("POST", "/api/v1/auth/signup"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/agents"),
    ("GET", "/api/v1/agents/invite/validate"),
    ("GET", "/api/v1/users/roles/list"),
]

# Expected status for unauthenticated / invalid requests (Step 2, 12)
EXPECTED_STATUS = {
    "health_ok": 200,
    "properties_list_ok": 200,
    "properties_exclusive_ok": 200,
    "location_taxonomy_ok": 200,
    "geo_search_ok": 200,
    "property_detail_404": 404,
    "auth_signup_validation_error": 422,
    "auth_me_unauthorized": 403,
    "auth_logout_unauthorized": 403,
    "agents_list_unauthorized": 403,
    "users_list_unauthorized": 403,
}

# Required top-level keys in success responses (Step 13 – schema stability)
SUCCESS_RESPONSE_KEYS = ["data"]
STANDARD_RESPONSE_KEYS = ["success", "message", "data", "error", "meta"]
PROPERTY_SEARCH_RESPONSE_KEYS = ["items", "total", "page", "pageSize"]
LOCATION_RESPONSE_KEYS = ["data", "total"]
