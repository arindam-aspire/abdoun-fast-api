"""API v1 router composition.

This module wires all v1 route modules into a single FastAPI `APIRouter`.
Route prefixes and tags are centralized in `app/utils/constants.py` (`ApiRoutes`).

Domain routers live in `app.domains` and re-export the same legacy `APIRouter`
instances where applicable; behavior is unchanged when feature flags are enabled.
"""

from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    admin_properties,
    admin_property_submissions,
    agent,
    agent_properties,
    agents,
    agency,
    auth,
    favorites,
    leads,
    locations,
    owners,
    properties,
    property_submissions,
    property_taxonomy,
    recent_views,
    notifications,
    notification_settings,
    saved_searches,
    search,
    uploads,
    users,
)
from app.core.config import get_settings
from app.domains.properties import (
    properties_router as refactored_properties_routes,
    search_router as refactored_search_routes,
)
from app.domains.taxonomy.router import router as refactored_taxonomy_router
from app.utils.constants import ApiRoutes

api_router = APIRouter()
settings = get_settings()

if settings.use_refactored_auth:
    from app.domains.auth import auth_router as _auth_router
else:
    _auth_router = auth.router
api_router.include_router(_auth_router, prefix=ApiRoutes.AUTH_PREFIX, tags=[ApiRoutes.AUTH_TAG])
api_router.include_router(agency.router, prefix=ApiRoutes.AGENCY_PREFIX, tags=[ApiRoutes.AGENCY_TAG])

if settings.use_refactored_agents:
    from app.domains.agents import agent_router as _agent_router
    from app.domains.agents import agents_router as _agents_router
else:
    _agent_router = agent.router
    _agents_router = agents.router
api_router.include_router(_agent_router, prefix=ApiRoutes.AGENT_PREFIX, tags=[ApiRoutes.AGENT_TAG])
api_router.include_router(_agents_router, prefix=ApiRoutes.AGENTS_PREFIX, tags=[ApiRoutes.AGENTS_TAG])

if settings.use_refactored_admin:
    from app.domains.admin import admin_dashboard_router as _admin_dashboard_router
else:
    _admin_dashboard_router = admin.router
api_router.include_router(
    _admin_dashboard_router,
    prefix=ApiRoutes.ADMIN_PREFIX,
    tags=[ApiRoutes.ADMIN_TAG],
)

if settings.use_refactored_personalization:
    from app.domains.personalization import recent_views_router as _recent_views_router
else:
    _recent_views_router = recent_views.router
api_router.include_router(
    _recent_views_router,
    prefix=ApiRoutes.USERS_PREFIX,
    tags=[ApiRoutes.USERS_TAG],
)

if settings.use_refactored_users:
    from app.domains.users import users_router as _users_router
else:
    _users_router = users.router
api_router.include_router(_users_router, prefix=ApiRoutes.USERS_PREFIX, tags=[ApiRoutes.USERS_TAG])

if settings.use_refactored_owners:
    from app.domains.owners import owners_router as _owners_router
else:
    _owners_router = owners.router
api_router.include_router(_owners_router, prefix=ApiRoutes.OWNERS_PREFIX, tags=[ApiRoutes.OWNERS_TAG])

if settings.use_refactored_personalization:
    from app.domains.personalization import favorites_router as _favorites_router
    from app.domains.personalization import saved_searches_router as _saved_searches_router
else:
    _favorites_router = favorites.router
    _saved_searches_router = saved_searches.router
api_router.include_router(
    _favorites_router,
    prefix=ApiRoutes.FAVORITES_PREFIX,
    tags=[ApiRoutes.FAVORITES_TAG],
)
api_router.include_router(
    _saved_searches_router,
    prefix=ApiRoutes.SAVED_SEARCHES_PREFIX,
    tags=[ApiRoutes.SAVED_SEARCHES_TAG],
)

# Phase 1: In-app Notifications (polling-based)
api_router.include_router(
    notifications.router,
    prefix=ApiRoutes.NOTIFICATIONS_PREFIX,
    tags=[ApiRoutes.NOTIFICATIONS_TAG],
)
api_router.include_router(
    notification_settings.router,
    prefix=ApiRoutes.NOTIFICATION_SETTINGS_PREFIX,
    tags=[ApiRoutes.NOTIFICATION_SETTINGS_TAG],
)

if settings.use_refactored_submissions:
    from app.domains.submissions import (
        admin_property_submissions_router as _admin_property_submissions_router,
        property_submissions_router as _property_submissions_router,
    )
else:
    _property_submissions_router = property_submissions.router
    _admin_property_submissions_router = admin_property_submissions.router
api_router.include_router(
    _property_submissions_router,
    prefix=ApiRoutes.PROPERTY_SUBMISSIONS_PREFIX,
    tags=[ApiRoutes.PROPERTY_SUBMISSIONS_TAG],
)
api_router.include_router(
    _admin_property_submissions_router,
    prefix=ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_PREFIX,
    tags=[ApiRoutes.ADMIN_PROPERTY_SUBMISSIONS_TAG],
)

if settings.use_refactored_admin:
    from app.domains.admin import admin_properties_router as _admin_properties_router
else:
    _admin_properties_router = admin_properties.router
api_router.include_router(
    _admin_properties_router,
    prefix=ApiRoutes.ADMIN_PREFIX,
    tags=[ApiRoutes.ADMIN_TAG],
)

if settings.use_refactored_uploads:
    from app.domains.uploads import uploads_router as _uploads_router
else:
    _uploads_router = uploads.router
api_router.include_router(_uploads_router, prefix=ApiRoutes.UPLOADS_PREFIX, tags=[ApiRoutes.UPLOADS_TAG])

api_router.include_router(
    agent_properties.router,
    prefix=ApiRoutes.AGENT_PROPERTIES_PREFIX,
    tags=[ApiRoutes.AGENT_PROPERTIES_TAG],
)

api_router.include_router(
    leads.public_router,
    tags=[ApiRoutes.LEADS_TAG],
)

api_router.include_router(
    leads.agent_router,
    prefix=ApiRoutes.AGENT_PREFIX,
    tags=[ApiRoutes.LEADS_TAG],
)

api_router.include_router(
    leads.admin_router,
    prefix=ApiRoutes.ADMIN_PREFIX,
    tags=[ApiRoutes.LEADS_TAG],
)

if settings.use_refactored_properties:
    api_router.include_router(
        refactored_properties_routes,
        prefix=ApiRoutes.PROPERTIES_PREFIX,
        tags=[ApiRoutes.PROPERTIES_TAG],
    )
    api_router.include_router(
        refactored_search_routes,
        prefix=ApiRoutes.PROPERTIES_PREFIX,
        tags=[ApiRoutes.SEARCH_TAG],
    )
else:
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

if settings.use_refactored_taxonomy:
    api_router.include_router(
        refactored_taxonomy_router,
        tags=[ApiRoutes.LOCATIONS_TAG, ApiRoutes.TAXONOMY_TAG],
    )
else:
    api_router.include_router(locations.router, tags=[ApiRoutes.LOCATIONS_TAG])

if not settings.use_refactored_taxonomy:
    api_router.include_router(property_taxonomy.router, tags=[ApiRoutes.TAXONOMY_TAG])
