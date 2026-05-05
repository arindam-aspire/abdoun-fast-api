"""Parity: admin dashboard, admin properties, users routers."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import admin as legacy_admin
from app.api.v1.routes import admin_properties as legacy_admin_properties
from app.api.v1.routes import users as legacy_users
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.admin import admin_dashboard_router, admin_properties_router
from app.domains.users import users_router
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_admin_users_route_signatures_match() -> None:
    v1 = SystemMessages.API_V1_PREFIX
    admin_base = f"{v1}{ApiRoutes.ADMIN_PREFIX}"
    users_base = f"{v1}{ApiRoutes.USERS_PREFIX}"

    legacy = FastAPI()
    legacy.include_router(legacy_admin.router, prefix=admin_base, tags=[ApiRoutes.ADMIN_TAG])
    legacy.include_router(
        legacy_admin_properties.router,
        prefix=admin_base,
        tags=[ApiRoutes.ADMIN_TAG],
    )
    legacy.include_router(legacy_users.router, prefix=users_base, tags=[ApiRoutes.USERS_TAG])

    ref = FastAPI()
    ref.include_router(admin_dashboard_router, prefix=admin_base, tags=[ApiRoutes.ADMIN_TAG])
    ref.include_router(
        admin_properties_router,
        prefix=admin_base,
        tags=[ApiRoutes.ADMIN_TAG],
    )
    ref.include_router(users_router, prefix=users_base, tags=[ApiRoutes.USERS_TAG])

    assert_route_parity(legacy, ref)
