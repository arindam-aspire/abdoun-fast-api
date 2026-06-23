from fastapi import APIRouter

from app.api.v1.routes import (
    admin_properties,
    agency,
    agent_properties,
    agents,
    auth,
    properties,
    property_submissions,
    search,
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



