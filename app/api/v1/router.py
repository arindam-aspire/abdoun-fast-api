"""API v1 router composition.

This module wires all v1 route modules into a single FastAPI `APIRouter`.
Route prefixes and tags are centralized in `app/utils/constants.py` (`ApiRoutes`).
"""

from fastapi import APIRouter

from app.api.v1.routes import (
    properties,
    search,
    locations,
    property_taxonomy,
    auth,
    agents,
    admin,
    users,
    owners,
    favorites,
    saved_searches,
    recent_views,
    property_submissions,
    admin_property_submissions,
    uploads,
    agent_properties,
)
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
    admin.router,
    prefix=ApiRoutes.ADMIN_PREFIX,
    tags=[ApiRoutes.ADMIN_TAG],
)

api_router.include_router(
    recent_views.router,
    prefix=ApiRoutes.USERS_PREFIX,
    tags=[ApiRoutes.USERS_TAG],
)

api_router.include_router(
    users.router,
    prefix=ApiRoutes.USERS_PREFIX,
    tags=[ApiRoutes.USERS_TAG],
)

api_router.include_router(
    owners.router,
    prefix=ApiRoutes.OWNERS_PREFIX,
    tags=[ApiRoutes.OWNERS_TAG],
)

api_router.include_router(
    favorites.router,
    prefix=ApiRoutes.FAVORITES_PREFIX,
    tags=[ApiRoutes.FAVORITES_TAG],
)

api_router.include_router(
    saved_searches.router,
    prefix=ApiRoutes.SAVED_SEARCHES_PREFIX,
    tags=[ApiRoutes.SAVED_SEARCHES_TAG],
)

api_router.include_router(
    property_submissions.router,
    prefix=ApiRoutes.PROPERTY_SUBMISSIONS_PREFIX,
    tags=[ApiRoutes.PROPERTY_SUBMISSIONS_TAG],
)

api_router.include_router(
    admin_property_submissions.router,
    prefix=ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_PREFIX,
    tags=[ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_TAG],
)

api_router.include_router(
    uploads.router,
    prefix=ApiRoutes.UPLOADS_PREFIX,
    tags=[ApiRoutes.UPLOADS_TAG],
)

api_router.include_router(
    agent_properties.router,
    prefix=ApiRoutes.AGENT_PROPERTIES_PREFIX,
    tags=[ApiRoutes.AGENT_PROPERTIES_TAG],
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

api_router.include_router(
    property_taxonomy.router,
    tags=[ApiRoutes.TAXONOMY_TAG],
)

