"""Parity: personalization routers (favorites, saved searches, recent views)."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import favorites, recent_views, saved_searches
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.personalization import (
    favorites_router,
    recent_views_router,
    saved_searches_router,
)
from tests.refactor_parity.route_parity_utils import assert_route_parity


def _v1_base() -> str:
    return SystemMessages.API_V1_PREFIX


def test_personalization_route_signatures_match() -> None:
    base = _v1_base()
    legacy = FastAPI()
    legacy.include_router(
        recent_views.router,
        prefix=f"{base}{ApiRoutes.USERS_PREFIX}",
        tags=[ApiRoutes.USERS_TAG],
    )
    legacy.include_router(
        favorites.router,
        prefix=f"{base}{ApiRoutes.FAVORITES_PREFIX}",
        tags=[ApiRoutes.FAVORITES_TAG],
    )
    legacy.include_router(
        saved_searches.router,
        prefix=f"{base}{ApiRoutes.SAVED_SEARCHES_PREFIX}",
        tags=[ApiRoutes.SAVED_SEARCHES_TAG],
    )

    ref = FastAPI()
    ref.include_router(
        recent_views_router,
        prefix=f"{base}{ApiRoutes.USERS_PREFIX}",
        tags=[ApiRoutes.USERS_TAG],
    )
    ref.include_router(
        favorites_router,
        prefix=f"{base}{ApiRoutes.FAVORITES_PREFIX}",
        tags=[ApiRoutes.FAVORITES_TAG],
    )
    ref.include_router(
        saved_searches_router,
        prefix=f"{base}{ApiRoutes.SAVED_SEARCHES_PREFIX}",
        tags=[ApiRoutes.SAVED_SEARCHES_TAG],
    )

    assert_route_parity(legacy, ref)
