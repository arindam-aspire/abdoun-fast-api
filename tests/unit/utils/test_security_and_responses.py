from __future__ import annotations

from typing import Any, cast

import pytest

from app.utils.responses import create_error_response, create_success_response
from app.utils.security import validate_input_length
from app.utils.status_codes import HTTPStatus
from app.utils.constants import ErrorMessages
from app.utils.constants import SuccessMessages


def test_validate_input_length_raises_on_none() -> None:
    with pytest.raises(ValueError):
        validate_input_length(cast(Any, None), 10)


def test_validate_input_length_truncates_when_too_long() -> None:
    assert validate_input_length("x" * 20, 10) == "x" * 10


def test_validate_input_length_strips_and_returns_when_within_limit() -> None:
    assert validate_input_length("  hello  ", 10) == "hello"


def test_create_success_response_wraps_data_and_message() -> None:
    r = create_success_response(data={"k": "v"}, message=SuccessMessages.LOGIN_SUCCESSFUL)
    assert r.success is True
    assert r.data == {"k": "v"}
    assert r.message == SuccessMessages.LOGIN_SUCCESSFUL


def test_create_error_response_sets_error_fields() -> None:
    r = create_error_response(
        error=ErrorMessages.REQUEST_FAILED,
        detail=ErrorMessages.VALIDATION_ERROR,
        status_code=HTTPStatus.BAD_REQUEST,
    )
    assert r.success is False
    assert r.error == ErrorMessages.REQUEST_FAILED
    assert r.detail == ErrorMessages.VALIDATION_ERROR
    assert r.status_code == HTTPStatus.BAD_REQUEST

