"""Parity: property submissions + admin property submissions routers."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import admin_property_submissions as legacy_aps
from app.api.v1.routes import property_submissions as legacy_ps
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.submissions import (
    admin_property_submissions_router,
    property_submissions_router,
)
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_submissions_route_signatures_match() -> None:
    v1 = SystemMessages.API_V1_PREFIX
    legacy = FastAPI()
    legacy.include_router(
        legacy_ps.router,
        prefix=f"{v1}{ApiRoutes.PROPERTY_SUBMISSIONS_PREFIX}",
        tags=[ApiRoutes.PROPERTY_SUBMISSIONS_TAG],
    )
    legacy.include_router(
        legacy_aps.router,
        prefix=f"{v1}{ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_PREFIX}",
        tags=[ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_TAG],
    )
    ref = FastAPI()
    ref.include_router(
        property_submissions_router,
        prefix=f"{v1}{ApiRoutes.PROPERTY_SUBMISSIONS_PREFIX}",
        tags=[ApiRoutes.PROPERTY_SUBMISSIONS_TAG],
    )
    ref.include_router(
        admin_property_submissions_router,
        prefix=f"{v1}{ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_PREFIX}",
        tags=[ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_TAG],
    )
    assert_route_parity(legacy, ref)
