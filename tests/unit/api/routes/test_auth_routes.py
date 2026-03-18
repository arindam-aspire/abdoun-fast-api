"""Unit tests for app.api.v1.routes.auth edge/deprecated branches."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.routes import auth as auth_module
from app.utils.log_messages import LogMessages, format_log_message


def test_signup_admin_logs_deprecated_endpoint_warning() -> None:
    with patch.object(auth_module.api_logger, "warning") as mock_warning:
        with pytest.raises(HTTPException):
            auth_module.signup_admin(
                user_in=object(),
                current_user=object(),
                service=object(),
            )
        mock_warning.assert_called_once_with(
            format_log_message(LogMessages.ApiRoutes.AUTH_DEPRECATED_ADMIN_SIGNUP)
        )

