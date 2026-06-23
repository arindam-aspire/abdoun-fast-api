from fastapi import APIRouter

from app.api.v1.routes import (
    admin_properties,
    agency,
    agent_properties,
    agents,
    audit_logs,
    deal_closures,
    favorites,
    auth,
    leads,
    properties,
    property_submissions,
    public_catalog,
    saved_searches,
    search,
    notifications,
    uploads,
    users,
)

api_router = APIRouter()

api_router.include_router(
    properties.router,
    prefix="/properties",
    tags=["properties"],
)

api_router.include_router(
    search.router,
    tags=["search"],
)

api_router.include_router(
    public_catalog.router,
    tags=["public-catalog"],
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    agency.router,
    prefix="/agency",
    tags=["agency"],
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
)

api_router.include_router(
    favorites.router,
    prefix="/favorites",
    tags=["favorites"],
)

api_router.include_router(
    saved_searches.router,
    prefix="/saved-searches",
    tags=["saved-searches"],
)

api_router.include_router(
    leads.router,
    prefix="/leads",
    tags=["leads"],
)

api_router.include_router(
    deal_closures.router,
    prefix="/deal-closures",
    tags=["deal-closures"],
)

api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["notifications"],
)

api_router.include_router(
    audit_logs.router,
    prefix="/audit-logs",
    tags=["audit-logs"],
)

api_router.include_router(
    uploads.router,
    prefix="/uploads",
    tags=["uploads"],
)

api_router.include_router(
    agents.router,
    prefix="/agents",
    tags=["agents"],
)

api_router.include_router(
    property_submissions.router,
    prefix="/property-submissions",
    tags=["property-submissions"],
)

api_router.include_router(
    agent_properties.router,
    prefix="/agent-properties",
    tags=["agent-properties"],
)

api_router.include_router(
    admin_properties.router,
    prefix="/admin",
    tags=["admin-properties"],
)



