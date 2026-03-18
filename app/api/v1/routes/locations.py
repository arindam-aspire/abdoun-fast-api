"""
API endpoints for cities and areas (locations)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps.locations import get_location_service
from app.core.limiter import limiter
from app.services.location_service import LocationService
from app.utils.constants import ApiDocs, RateLimits


router = APIRouter()


@router.get("/cities")
@limiter.limit(RateLimits.PUBLIC_READ_HIGH)
def list_cities(
    request: Request,
    service: LocationService = Depends(get_location_service),
) -> dict:
    """Return a list of active cities."""
    return service.list_cities()


@router.get("/areas")
@limiter.limit(RateLimits.PUBLIC_READ_HIGH)
def list_areas(
    request: Request,
    city: Optional[str] = Query(
        None, description=ApiDocs.FILTER_AREAS_BY_CITY_NAME
    ),
    service: LocationService = Depends(get_location_service),
) -> dict:
    """Return a list of areas, optionally filtered by city."""
    return service.list_areas(city=city)

