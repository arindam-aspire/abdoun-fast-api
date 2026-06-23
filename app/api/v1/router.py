from fastapi import APIRouter

from app.api.v1.routes import agency, auth, properties, search, users

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



