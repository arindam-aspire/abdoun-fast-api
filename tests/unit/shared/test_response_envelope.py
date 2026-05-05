"""Unit tests for the standard API response envelope."""

from __future__ import annotations

from app.domains.shared.pagination import calculate_pagination
from app.domains.shared.responses import merge_meta, pagination_public
from app.utils.constants import SuccessMessages
from app.utils.responses import ApiErrorBody, create_error_response, create_success_response


def test_pagination_public_matches_contract() -> None:
    meta = calculate_pagination(page=2, page_size=10, total=45)
    p = pagination_public(meta)
    assert p == {
        "total": 45,
        "page": 2,
        "pageSize": 10,
        "totalPages": 5,
        "hasNext": True,
        "hasPrevious": True,
    }


def test_merge_meta_skips_none_and_merges() -> None:
    assert merge_meta(None, None) == {}
    assert merge_meta({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert merge_meta({"a": 1}, {"a": 2}) == {"a": 2}


def test_create_success_response_includes_meta_and_null_error() -> None:
    r = create_success_response(data={"x": 1}, message=None)
    assert r.success is True
    assert r.message is None
    assert r.data == {"x": 1}
    assert r.error is None
    assert r.meta == {}


def test_create_success_response_merges_pagination() -> None:
    meta = calculate_pagination(page=1, page_size=20, total=0)
    r = create_success_response(data=[], message=SuccessMessages.LOGIN_SUCCESSFUL, pagination=meta)
    assert r.meta["pagination"]["total"] == 0
    assert r.meta["pagination"]["page"] == 1
    assert r.meta["pagination"]["pageSize"] == 20
    assert r.meta["pagination"]["hasNext"] is False


def test_create_success_response_meta_merge_with_pagination() -> None:
    meta = calculate_pagination(page=1, page_size=10, total=5)
    r = create_success_response(data={}, message=None, meta={"traceId": "t1"}, pagination=meta)
    assert r.meta["traceId"] == "t1"
    assert "pagination" in r.meta


def test_create_error_response_envelope() -> None:
    r = create_error_response("Bad", detail="More", status_code=400)
    assert r.success is False
    assert r.message == "Bad"
    assert r.data is None
    assert isinstance(r.error, ApiErrorBody)
    assert r.error.code == "HTTP_400"
    assert r.error.details["detail"] == "More"
    assert r.meta == {}


def test_model_dump_field_order_keys() -> None:
    r = create_success_response(data={"k": "v"}, message="m")
    keys = list(r.model_dump().keys())
    assert keys == ["success", "message", "data", "error", "meta"]
