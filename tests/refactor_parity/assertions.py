"""Common assertions for parity comparisons."""

from __future__ import annotations

from typing import Any


def normalize_dynamic_fields(payload: Any) -> Any:
    dynamic_keys = {"id", "created_at", "updated_at", "expires_at", "token", "signed_url"}
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in dynamic_keys:
                normalized[key] = f"<normalized:{key}>"
            else:
                normalized[key] = normalize_dynamic_fields(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_dynamic_fields(item) for item in payload]
    return payload


def assert_status_parity(legacy_status: int, refactored_status: int) -> None:
    assert legacy_status == refactored_status


def assert_json_shape_parity(legacy_json: Any, refactored_json: Any) -> None:
    assert normalize_dynamic_fields(legacy_json) == normalize_dynamic_fields(refactored_json)


def assert_response_headers_parity(
    legacy_headers: dict[str, str],
    refactored_headers: dict[str, str],
    optional: bool = True,
) -> None:
    header_keys = {"content-type", "cache-control"}
    if optional:
        for key in header_keys:
            if key in legacy_headers and key in refactored_headers:
                assert legacy_headers[key] == refactored_headers[key]
    else:
        for key in header_keys:
            assert legacy_headers.get(key) == refactored_headers.get(key)

