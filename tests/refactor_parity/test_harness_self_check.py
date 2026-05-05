from fastapi import APIRouter

from tests.refactor_parity.assertions import (
    assert_json_shape_parity,
    assert_status_parity,
    normalize_dynamic_fields,
)
from tests.refactor_parity.parity_client import (
    ParityClient,
    build_legacy_client,
    build_refactored_client,
)


def test_normalize_dynamic_fields_masks_runtime_values() -> None:
    payload = {"id": 99, "created_at": "2026-01-01", "nested": {"token": "abc"}}
    normalized = normalize_dynamic_fields(payload)
    assert normalized["id"] == "<normalized:id>"
    assert normalized["nested"]["token"] == "<normalized:token>"


def test_parity_client_can_compare_same_route_shape() -> None:
    router = APIRouter()

    @router.get("/parity-self-check")
    def parity_self_check():
        return {"ok": True, "id": 123}

    legacy = build_refactored_client(router)
    refactored = build_refactored_client(router)
    parity = ParityClient(legacy_client=legacy, refactored_client=refactored)

    legacy_resp, refactored_resp = parity.request("GET", "/parity-self-check")
    assert_status_parity(legacy_resp.status_code, refactored_resp.status_code)
    assert_json_shape_parity(legacy_resp.json(), refactored_resp.json())


def test_legacy_app_client_bootstraps() -> None:
    with build_legacy_client() as client:
        response = client.get("/health")
        assert response.status_code in {200, 404}

