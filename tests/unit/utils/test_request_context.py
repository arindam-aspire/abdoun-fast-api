from __future__ import annotations

import re

from app.utils.request_context import (
    get_request_id,
    new_request_id,
    sanitize_incoming_request_id,
    set_request_id,
)


def test_new_request_id_is_uuid() -> None:
    rid = new_request_id()
    assert isinstance(rid, str)
    assert re.fullmatch(r"[0-9a-fA-F-]{36}", rid)


def test_set_and_get_request_id_roundtrip() -> None:
    set_request_id("test_request_id_123456")
    try:
        assert get_request_id() == "test_request_id_123456"
    finally:
        set_request_id(None)


def test_sanitize_incoming_request_id_accepts_uuid() -> None:
    assert sanitize_incoming_request_id("00000000-0000-0000-0000-000000000000") == (
        "00000000-0000-0000-0000-000000000000"
    )


def test_sanitize_incoming_request_id_accepts_safe_token() -> None:
    assert sanitize_incoming_request_id("abcDEF0123_-abcDEF0123_-") == "abcDEF0123_-abcDEF0123_-"


def test_sanitize_incoming_request_id_rejects_blank_and_unsafe_values() -> None:
    assert sanitize_incoming_request_id(None) is None
    assert sanitize_incoming_request_id("") is None
    assert sanitize_incoming_request_id("   ") is None
    assert sanitize_incoming_request_id("short") is None  # < 16 chars
    assert sanitize_incoming_request_id("contains spaces 123456") is None
    assert sanitize_incoming_request_id("../path-traversal-123456") is None

