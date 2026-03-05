from fastapi import APIRouter

from app.api.v1.routes import properties, search, locations, auth, agents, users

api_router = APIRouter()

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    agents.router,
    prefix="/agents",
    tags=["agents"],
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
)

api_router.include_router(
    properties.router,
    prefix="/properties",
    tags=["properties"],
)

api_router.include_router(
    search.router,
    prefix="/properties",
    tags=["search"],
)

api_router.include_router(
    locations.router,
    tags=["locations"],
)

