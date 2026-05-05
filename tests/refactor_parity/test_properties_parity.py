"""Parity: legacy properties + search routers vs refactored composite router."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.v1.deps.properties import get_property_search_service
from app.api.v1.deps.search import get_geo_search_service
from app.api.v1.routes import properties as legacy_properties
from app.api.v1.routes import search as legacy_search
from app.schemas.property import PropertyListResponse, PropertySearchRequest, PropertySearchResponse
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.properties import properties_router, search_router
from tests.refactor_parity.assertions import assert_json_shape_parity, assert_status_parity


def _properties_base_path() -> str:
    return f"{SystemMessages.API_V1_PREFIX}{ApiRoutes.PROPERTIES_PREFIX}"


def _route_signatures(app: FastAPI) -> set[tuple[str, str]]:
    sig: set[tuple[str, str]] = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods or []:
                if method == "HEAD":
                    continue
                sig.add((method.upper(), route.path))
    return sig


def test_properties_domain_route_signatures_match() -> None:
    base = _properties_base_path()
    legacy_app = FastAPI()
    legacy_app.include_router(legacy_properties.router, prefix=base)
    legacy_app.include_router(legacy_search.router, prefix=base)

    ref_app = FastAPI()
    ref_app.include_router(properties_router, prefix=base)
    ref_app.include_router(search_router, prefix=base)

    assert _route_signatures(legacy_app) == _route_signatures(ref_app)


def test_list_properties_response_parity_with_mocked_service() -> None:
    base = _properties_base_path()
    expected = PropertySearchResponse(items=[], total=0, page=1, pageSize=12)

    class _FakeSearch:
        def search(self, params):  # noqa: ANN001
            return expected

    legacy_app = FastAPI()
    legacy_app.include_router(legacy_properties.router, prefix=base)
    legacy_app.dependency_overrides[get_property_search_service] = lambda: _FakeSearch()

    ref_app = FastAPI()
    ref_app.include_router(properties_router, prefix=base)
    ref_app.include_router(search_router, prefix=base)
    ref_app.dependency_overrides[get_property_search_service] = lambda: _FakeSearch()

    leg = TestClient(legacy_app).get(f"{base}")
    ref = TestClient(ref_app).get(f"{base}")
    assert_status_parity(leg.status_code, ref.status_code)
    assert_json_shape_parity(leg.json(), ref.json())


def test_geo_search_response_parity_with_mocked_service() -> None:
    base = _properties_base_path()
    expected = PropertyListResponse(items=[], total=0)

    class _FakeGeo:
        def search(self, payload: PropertySearchRequest) -> PropertyListResponse:
            return expected

    legacy_app = FastAPI()
    legacy_app.include_router(legacy_search.router, prefix=base)
    legacy_app.dependency_overrides[get_geo_search_service] = lambda: _FakeGeo()

    ref_app = FastAPI()
    ref_app.include_router(properties_router, prefix=base)
    ref_app.include_router(search_router, prefix=base)
    ref_app.dependency_overrides[get_geo_search_service] = lambda: _FakeGeo()

    payload: dict = {
        "mode": "bounds",
        "bounds": {
            "min_lng": 35.9,
            "min_lat": 31.9,
            "max_lng": 36.0,
            "max_lat": 32.0,
        },
        "limit": 10,
    }
    leg = TestClient(legacy_app).post(f"{base}/geo-search", json=payload)
    ref = TestClient(ref_app).post(f"{base}/geo-search", json=payload)
    assert_status_parity(leg.status_code, ref.status_code)
    assert_json_shape_parity(leg.json(), ref.json())
