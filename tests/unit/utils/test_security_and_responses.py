from __future__ import annotations

from typing import Any, cast

import pytest

from app.utils.responses import create_error_response, create_success_response
from app.utils.security import validate_input_length


def test_validate_input_length_raises_on_none() -> None:
    with pytest.raises(ValueError):
        validate_input_length(cast(Any, None), 10)


def test_validate_input_length_truncates_when_too_long() -> None:
    assert validate_input_length("x" * 20, 10) == "x" * 10


def test_validate_input_length_strips_and_returns_when_within_limit() -> None:
    assert validate_input_length("  hello  ", 10) == "hello"


def test_create_success_response_wraps_data_and_message() -> None:
    r = create_success_response(data={"k": "v"}, message="ok")
    assert r.success is True
    assert r.data == {"k": "v"}
    assert r.message == "ok"


def test_create_error_response_sets_error_fields() -> None:
    r = create_error_response(error="bad", detail="nope", status_code=400)
    assert r.success is False
    assert r.error == "bad"
    assert r.detail == "nope"
    assert r.status_code == 400

