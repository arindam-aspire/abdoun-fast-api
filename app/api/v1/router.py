from fastapi import APIRouter

from app.api.v1.routes import properties, search, locations

api_router = APIRouter()

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



