"""Parity: owners router."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import owners as legacy_owners
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.owners import owners_router
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_owners_route_signatures_match() -> None:
    base = f"{SystemMessages.API_V1_PREFIX}{ApiRoutes.OWNERS_PREFIX}"
    legacy = FastAPI()
    legacy.include_router(legacy_owners.router, prefix=base, tags=[ApiRoutes.OWNERS_TAG])
    ref = FastAPI()
    ref.include_router(owners_router, prefix=base, tags=[ApiRoutes.OWNERS_TAG])
    assert_route_parity(legacy, ref)
