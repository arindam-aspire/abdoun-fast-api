"""API v1 router composition.

This module wires all v1 route modules into a single FastAPI `APIRouter`.
Route prefixes and tags are centralized in `app/utils/constants.py` (`ApiRoutes`).
"""

from fastapi import APIRouter

from app.api.v1.routes import properties, search, locations, auth, agents, users
from app.utils.constants import ApiRoutes

api_router = APIRouter()

api_router.include_router(
    auth.router,
    prefix=ApiRoutes.AUTH_PREFIX,
    tags=[ApiRoutes.AUTH_TAG],
)

api_router.include_router(
    agents.router,
    prefix=ApiRoutes.AGENTS_PREFIX,
    tags=[ApiRoutes.AGENTS_TAG],
)

api_router.include_router(
    users.router,
    prefix=ApiRoutes.USERS_PREFIX,
    tags=[ApiRoutes.USERS_TAG],
)

api_router.include_router(
    properties.router,
    prefix=ApiRoutes.PROPERTIES_PREFIX,
    tags=[ApiRoutes.PROPERTIES_TAG],
)

api_router.include_router(
    search.router,
    prefix=ApiRoutes.PROPERTIES_PREFIX,
    tags=[ApiRoutes.SEARCH_TAG],
)

api_router.include_router(
    locations.router,
    tags=[ApiRoutes.LOCATIONS_TAG],
)

