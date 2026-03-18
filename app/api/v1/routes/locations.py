"""
API endpoints for cities and areas (locations)
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.locations import get_location_service
from app.services.location_service import LocationService
from app.utils.constants import ApiDocs


router = APIRouter()


@router.get("/cities")
def list_cities(
    service: Annotated[LocationService, Depends(get_location_service)],
) -> dict:
    """Return a list of active cities."""
    return service.list_cities()


@router.get("/areas")
def list_areas(
    service: Annotated[LocationService, Depends(get_location_service)],
    city: Annotated[Optional[str], Query(description=ApiDocs.FILTER_AREAS_BY_CITY_NAME)] = None,
) -> dict:
    """Return a list of areas, optionally filtered by city."""
    return service.list_areas(city=city)

