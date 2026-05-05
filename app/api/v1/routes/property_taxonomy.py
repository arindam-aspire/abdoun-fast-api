"""API endpoints for property taxonomy (categories with nested property types)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.property_taxonomy import get_property_taxonomy_service
from app.services.property_taxonomy_service import PropertyTaxonomyService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get("/property-taxonomy")
def get_property_taxonomy(
    service: Annotated[PropertyTaxonomyService, Depends(get_property_taxonomy_service)],
) -> StandardResponse[dict]:
    """Return categories with their property types in one response."""
    return create_success_response(data=service.get_property_taxonomy(), message=None)

