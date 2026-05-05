"""API endpoints for location taxonomy (cities with nested areas)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.locations import get_location_service
from app.services.location_service import LocationService
from app.utils.responses import StandardResponse, create_success_response


router = APIRouter()


@router.get("/location-taxonomy")
def get_location_taxonomy(
    service: Annotated[LocationService, Depends(get_location_service)],
) -> StandardResponse[dict]:
    """Return active cities with their areas in one response."""
    return create_success_response(data=service.get_location_taxonomy(), message=None)

