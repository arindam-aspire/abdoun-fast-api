"""Fixtures for refactor parity tests."""

from __future__ import annotations

import pytest

from app.core.auth import get_current_user
from app.main import app
from tests.refactor_parity.auth_overrides import fake_current_user_async


@pytest.fixture()
def fake_current_user_override():
    app.dependency_overrides[get_current_user] = fake_current_user_async
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)

