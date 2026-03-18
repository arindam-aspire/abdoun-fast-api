"""Unit tests for app.api.v1.routes.agents helpers and compat branches."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.routes import agents as agents_module
from app.utils.log_messages import LogMessages, format_log_message


def test_sanitize_validation_errors_base_exception():
    err = Exception("bad")
    out = agents_module._sanitize_validation_errors([{"type": "x", "ctx": {"err": err}}])
    assert out == [{"type": "x", "ctx": {"err": "bad"}}]


def test_sanitize_validation_errors_type_error():
    # Value that json.dumps() cannot serialize (e.g. set) triggers TypeError branch
    out = agents_module._sanitize_validation_errors([{"type": "x", "ctx": {"key": {1, 2, 3}}}])
    assert out[0]["ctx"]["key"] == "{1, 2, 3}"


def test_sanitize_validation_errors_json_serializable():
    out = agents_module._sanitize_validation_errors([{"type": "x", "ctx": {"n": 42}}])
    assert out == [{"type": "x", "ctx": {"n": 42}}]


def test_sanitize_validation_errors_no_ctx():
    out = agents_module._sanitize_validation_errors([{"type": "y", "loc": ("a",)}])
    assert out == [{"type": "y", "loc": ("a",)}]


def test_submit_onboarding_compat_logs_when_token_missing() -> None:
    with patch.object(agents_module.api_logger, "warning") as mock_warning:
        with pytest.raises(HTTPException) as exc:
            agents_module.submit_onboarding_compat(
                payload={},
                token=None,
                service=object(),
            )
        assert exc.value.status_code == 400
        mock_warning.assert_called_once_with(
            format_log_message(LogMessages.ApiRoutes.AGENTS_ONBOARDING_COMPAT_MISSING_TOKEN)
        )


def test_submit_onboarding_compat_logs_when_validation_fails() -> None:
    with patch.object(agents_module.api_logger, "warning") as mock_warning:
        with pytest.raises(HTTPException) as exc:
            agents_module.submit_onboarding_compat(
                payload={"token": "tok"},  # missing required fields => ValidationError
                token=None,
                service=object(),
            )
        assert exc.value.status_code == 422
        mock_warning.assert_called_once()
        logged_msg = mock_warning.call_args[0][0]
        assert (
            logged_msg
            == format_log_message(
                LogMessages.ApiRoutes.AGENTS_ONBOARDING_COMPAT_VALIDATION_FAILED,
                error_count=len(exc.value.detail),
            )
        )
