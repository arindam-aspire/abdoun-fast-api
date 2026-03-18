"""Property listing and detail endpoints.

This router provides read-only property search endpoints that match the frontend
search contract, plus property detail and "similar properties" lookups.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps.properties import get_property_search_service
from app.core.limiter import limiter
from app.schemas.property import (
    PropertyDetail,
    PropertySearchParams,
    PropertySearchResponse,
)
from app.services.property_search_service import PropertySearchService
from app.utils.constants import ApiDocs, Defaults, RateLimits

router = APIRouter()


def get_property_search_params(
    status: Optional[str] = Query(None, description=ApiDocs.LISTING_TYPE_BUY_RENT),
    category: Optional[str] = Query(None, description=ApiDocs.PROPERTY_CATEGORY),
    type_slug: Optional[str] = Query(
        None, alias="type", description=ApiDocs.PROPERTY_TYPE_SLUG
    ),
    city: Optional[str] = Query(None, description=ApiDocs.CITY_NAME_LOWERCASE),
    locations: Optional[str] = Query(
        None, description=ApiDocs.LOCATIONS_CSV_LOWERCASE
    ),
    budget_min: Optional[str] = Query(
        None, alias="budgetMin", description=ApiDocs.BUDGET_MIN_JD_NUMERIC_STRING
    ),
    budget_max: Optional[str] = Query(
        None, alias="budgetMax", description=ApiDocs.BUDGET_MAX_JD_NUMERIC_STRING
    ),
    min_price: Optional[str] = Query(
        None, alias="minPrice", description=ApiDocs.MIN_PRICE_ALIAS
    ),
    max_price: Optional[str] = Query(
        None, alias="maxPrice", description=ApiDocs.MAX_PRICE_ALIAS
    ),
    exclusive: Optional[str] = Query(None, description=ApiDocs.EXCLUSIVE_FILTER),
    page: int = Query(1, ge=1, description=ApiDocs.PAGE_NUMBER_1_BASED),
    page_size: int = Query(
        12, alias="pageSize", ge=1, le=100, description=ApiDocs.ITEMS_PER_PAGE
    ),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
    """Build property search params from query arguments.

    Returns:
        `PropertySearchParams` instance suitable for `PropertySearchService.search()`.
    """
    return PropertySearchParams(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        exclusive=exclusive,
        page=page,
        page_size=page_size,
        lang=lang,
    )


def get_exclusive_property_search_params(
    status: Optional[str] = Query(None, description=ApiDocs.LISTING_TYPE_BUY_RENT),
    category: Optional[str] = Query(None, description=ApiDocs.PROPERTY_CATEGORY),
    type_slug: Optional[str] = Query(
        None, alias="type", description=ApiDocs.PROPERTY_TYPE_SLUG
    ),
    city: Optional[str] = Query(None, description=ApiDocs.CITY_NAME_LOWERCASE),
    locations: Optional[str] = Query(
        None, description=ApiDocs.LOCATIONS_CSV_LOWERCASE
    ),
    budget_min: Optional[str] = Query(
        None, alias="budgetMin", description=ApiDocs.BUDGET_MIN_JD_NUMERIC_STRING
    ),
    budget_max: Optional[str] = Query(
        None, alias="budgetMax", description=ApiDocs.BUDGET_MAX_JD_NUMERIC_STRING
    ),
    min_price: Optional[str] = Query(
        None, alias="minPrice", description=ApiDocs.MIN_PRICE_ALIAS
    ),
    max_price: Optional[str] = Query(
        None, alias="maxPrice", description=ApiDocs.MAX_PRICE_ALIAS
    ),
    page: int = Query(1, ge=1, description=ApiDocs.PAGE_NUMBER_1_BASED),
    page_size: int = Query(
        12, alias="pageSize", ge=1, le=100, description=ApiDocs.ITEMS_PER_PAGE
    ),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
    """Build property search params for exclusive listings only (exclusive=true).

    Returns:
        PropertySearchParams with exclusive fixed to "true".
    """
    return PropertySearchParams(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        exclusive="true",
        page=page,
        page_size=page_size,
        lang=lang,
    )


@router.get("", response_model=PropertySearchResponse)
@limiter.limit(RateLimits.PUBLIC_READ)
def list_properties(
    request: Request,
    params: Annotated[PropertySearchParams, Depends(get_property_search_params)],
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertySearchResponse:
    """Search properties with optional filters and pagination."""
    return service.search(params)


@router.get("/exclusive", response_model=PropertySearchResponse)
@limiter.limit(RateLimits.PUBLIC_READ)
def list_exclusive_properties(
    request: Request,
    params: Annotated[PropertySearchParams, Depends(get_exclusive_property_search_params)],
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertySearchResponse:
    """List exclusive properties with optional filters and pagination."""
    return service.search(params)


@router.get("/{property_id}/similar", response_model=PropertySearchResponse)
@limiter.limit(RateLimits.PUBLIC_ACTION)
def get_similar_properties(
    request: Request,
    property_id: str,  # FastAPI path params are always strings
    limit: int = Query(20, ge=1, le=50, description=ApiDocs.MAX_SIMILAR_PROPERTIES),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertySearchResponse:
    """Get similar properties for a given property."""
    return service.get_similar(property_id, limit=limit, lang=lang)


@router.get("/{property_id}", response_model=PropertyDetail)
@limiter.limit(RateLimits.PUBLIC_READ)
def get_property(
    request: Request,
    property_id: str,  # FastAPI path params are always strings
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertyDetail:
    """Get detailed information for a specific property."""
    return service.get_detail(property_id, lang=lang)
