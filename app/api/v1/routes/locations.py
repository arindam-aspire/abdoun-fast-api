"""
API endpoints for cities and areas (locations)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps.locations import get_location_service
from app.core.limiter import limiter
from app.services.location_service import LocationService


router = APIRouter()


@router.get("/cities")
@limiter.limit("120/minute")
def list_cities(
    request: Request,
    service: LocationService = Depends(get_location_service),
) -> dict:
    """
    Get list of all active cities.

    Returns a list of cities with their IDs and names.
    """
    return service.list_cities()


@router.get("/areas")
@limiter.limit("120/minute")
def list_areas(
    request: Request,
    city: Optional[str] = Query(
        None, description="Filter areas by city name (case-insensitive)"
    ),
    service: LocationService = Depends(get_location_service),
) -> dict:
    """
    Get list of areas, optionally filtered by city.

    If city parameter is provided, returns only areas in that city.
    Otherwise, returns all active areas.
    """
    return service.list_areas(city=city)

