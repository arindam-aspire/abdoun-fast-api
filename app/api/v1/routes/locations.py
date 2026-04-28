"""API endpoints for location taxonomy (cities with nested areas)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.locations import get_location_service
from app.services.location_service import LocationService


router = APIRouter()


@router.get("/location-taxonomy")
def get_location_taxonomy(
    service: Annotated[LocationService, Depends(get_location_service)],
) -> dict:
    """Return active cities with their areas in one response."""
    return service.get_location_taxonomy()

