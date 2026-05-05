"""Parity: auth router."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import auth as legacy_auth
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.auth import auth_router
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_auth_route_signatures_match() -> None:
    base = f"{SystemMessages.API_V1_PREFIX}{ApiRoutes.AUTH_PREFIX}"
    legacy = FastAPI()
    legacy.include_router(legacy_auth.router, prefix=base, tags=[ApiRoutes.AUTH_TAG])
    ref = FastAPI()
    ref.include_router(auth_router, prefix=base, tags=[ApiRoutes.AUTH_TAG])
    assert_route_parity(legacy, ref)
