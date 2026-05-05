"""Refactored taxonomy routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.domains.taxonomy.deps import get_taxonomy_service
from app.domains.taxonomy.service import TaxonomyService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get("/location-taxonomy")
def get_location_taxonomy(
    service: Annotated[TaxonomyService, Depends(get_taxonomy_service)],
) -> StandardResponse[dict]:
    return create_success_response(data=service.get_location_taxonomy(), message=None)


@router.get("/property-taxonomy")
def get_property_taxonomy(
    service: Annotated[TaxonomyService, Depends(get_taxonomy_service)],
) -> StandardResponse[dict]:
    return create_success_response(data=service.get_property_taxonomy(), message=None)

