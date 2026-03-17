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
from app.utils.constants import Defaults

router = APIRouter()


def get_property_search_params(
    status: Optional[str] = Query(None, description="Listing type: buy or rent"),
    category: Optional[str] = Query(None, description="One of: residential, commercial, land. On Hero, 'Land' is sent as lands."),
    type_slug: Optional[str] = Query(None, alias="type", description="Slugified property type (e.g., apartments, villas, residential-lands)"),
    city: Optional[str] = Query(None, description="City name, lowercase"),
    locations: Optional[str] = Query(None, description="Comma-separated area/neighborhood names, lowercase"),
    budget_min: Optional[str] = Query(None, alias="budgetMin", description="Minimum price in JD (numeric string)"),
    budget_max: Optional[str] = Query(None, alias="budgetMax", description="Maximum price in JD (numeric string)"),
    min_price: Optional[str] = Query(None, alias="minPrice", description="Alias for budgetMin (for hero search compatibility)"),
    max_price: Optional[str] = Query(None, alias="maxPrice", description="Alias for budgetMax (for hero search compatibility)"),
    exclusive: Optional[str] = Query(None, description="Filter by exclusive status (true/1 for exclusive only, false/0 for non-exclusive only)"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(12, alias="pageSize", ge=1, le=100, description="Items per page"),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
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
    status: Optional[str] = Query(None, description="Listing type: buy or rent"),
    category: Optional[str] = Query(None, description="One of: residential, commercial, land. On Hero, 'Land' is sent as lands."),
    type_slug: Optional[str] = Query(None, alias="type", description="Slugified property type (e.g., apartments, villas, residential-lands)"),
    city: Optional[str] = Query(None, description="City name, lowercase"),
    locations: Optional[str] = Query(None, description="Comma-separated area/neighborhood names, lowercase"),
    budget_min: Optional[str] = Query(None, alias="budgetMin", description="Minimum price in JD (numeric string)"),
    budget_max: Optional[str] = Query(None, alias="budgetMax", description="Maximum price in JD (numeric string)"),
    min_price: Optional[str] = Query(None, alias="minPrice", description="Alias for budgetMin (for hero search compatibility)"),
    max_price: Optional[str] = Query(None, alias="maxPrice", description="Alias for budgetMax (for hero search compatibility)"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(12, alias="pageSize", ge=1, le=100, description="Items per page"),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
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
@limiter.limit("60/minute")
def list_properties(
    request: Request,
    params: Annotated[PropertySearchParams, Depends(get_property_search_params)],
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertySearchResponse:
    """
    Search properties with optional filters and pagination.
    
    Matches the frontend search contract for Home Page and Search Results page.
    Supports both budgetMin/budgetMax and minPrice/maxPrice for compatibility.
    """
    return service.search(params)


@router.get("/exclusive", response_model=PropertySearchResponse)
@limiter.limit("60/minute")
def list_exclusive_properties(
    request: Request,
    params: Annotated[PropertySearchParams, Depends(get_exclusive_property_search_params)],
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertySearchResponse:
    """
    List exclusive properties with optional filters and pagination.
    
    Same as regular property list endpoint but only returns properties where is_exclusive = True.
    Uses the same response format and supports all the same filters.
    """
    return service.search(params)


@router.get("/{property_id}/similar", response_model=PropertySearchResponse)
@limiter.limit("30/minute")
def get_similar_properties(
    request: Request,
    property_id: str,  # FastAPI path params are always strings
    limit: int = Query(20, ge=1, le=50, description="Maximum number of similar properties to return"),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertySearchResponse:
    """
    Get similar properties based on the selected property.
    """
    return service.get_similar(property_id, limit=limit, lang=lang)


@router.get("/{property_id}", response_model=PropertyDetail)
@limiter.limit("60/minute")
def get_property(
    request: Request,
    property_id: str,  # FastAPI path params are always strings
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
    service: PropertySearchService = Depends(get_property_search_service),
) -> PropertyDetail:
    """
    Get detailed information about a specific property.
    """
    return service.get_detail(property_id, lang=lang)
