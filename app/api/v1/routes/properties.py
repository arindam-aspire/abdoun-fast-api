"""Property listing and detail endpoints.

This router provides read-only property search endpoints that match the frontend
search contract, plus property detail and "similar properties" lookups.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps.properties import get_property_search_service
from app.api.v1.deps.recent_views import get_recent_view_service
from app.api.v1.deps.security import get_current_user_optional
from app.domains.shared.pagination import calculate_pagination
from app.models.user import User
from app.schemas.property import (
    PropertyDetail,
    PropertySearchParams,
    PropertySearchResponse,
)
from app.services.property_search_service import PropertySearchService
from app.services.recent_view_service import RecentViewService
from app.utils.constants import ApiDocs, Defaults
from app.utils.logger import api_logger
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus

router = APIRouter()


def _build_property_search_params(
    *,
    status: Optional[str],
    category: Optional[str],
    type_slug: Optional[str],
    city: Optional[str],
    locations: Optional[str],
    search: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    radius: Optional[float],
    budget_min: Optional[str],
    budget_max: Optional[str],
    min_price: Optional[str],
    max_price: Optional[str],
    exclusive: Optional[str],
    page: int,
    page_size: int,
    lang: Optional[str],
) -> PropertySearchParams:
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Both lat and lng are required when using GPS coordinates.",
        )
    return PropertySearchParams(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        search=search,
        lat=lat,
        lng=lng,
        radius=radius,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        exclusive=exclusive,
        page=page,
        page_size=page_size,
        lang=lang,
    )


def get_property_search_params(
    status: Optional[str] = Query(None, description=ApiDocs.LISTING_TYPE_BUY_RENT),
    category: Optional[str] = Query(None, description=ApiDocs.PROPERTY_CATEGORY),
    type_slug: Optional[str] = Query(None, alias="type", description=ApiDocs.PROPERTY_TYPE_SLUG),
    city: Optional[str] = Query(None, description=ApiDocs.CITY_NAME_LOWERCASE),
    locations: Optional[str] = Query(None, description=ApiDocs.LOCATIONS_CSV_LOWERCASE),
    search: Optional[str] = Query(None, description=ApiDocs.PROPERTY_SEARCH_TEXT),
    lat: Optional[float] = Query(None, description=ApiDocs.PROPERTY_SEARCH_LAT),
    lng: Optional[float] = Query(None, description=ApiDocs.PROPERTY_SEARCH_LNG),
    radius: Optional[float] = Query(
        None,
        ge=0.1,
        le=500,
        description=ApiDocs.PROPERTY_SEARCH_RADIUS_KM,
    ),
    budget_min: Optional[str] = Query(None, alias="budgetMin", description=ApiDocs.BUDGET_MIN_JD_NUMERIC_STRING),
    budget_max: Optional[str] = Query(None, alias="budgetMax", description=ApiDocs.BUDGET_MAX_JD_NUMERIC_STRING),
    min_price: Optional[str] = Query(None, alias="minPrice", description=ApiDocs.MIN_PRICE_ALIAS),
    max_price: Optional[str] = Query(None, alias="maxPrice", description=ApiDocs.MAX_PRICE_ALIAS),
    exclusive: Optional[str] = Query(None, description=ApiDocs.EXCLUSIVE_FILTER),
    page: int = Query(1, ge=1, description=ApiDocs.PAGE_NUMBER_1_BASED),
    page_size: int = Query(12, alias="pageSize", ge=1, le=100, description=ApiDocs.ITEMS_PER_PAGE),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
    """Build property search params from query arguments.

    Returns:
        `PropertySearchParams` instance suitable for `PropertySearchService.search()`.
    """
    return _build_property_search_params(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        search=search,
        lat=lat,
        lng=lng,
        radius=radius,
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
    type_slug: Optional[str] = Query(None, alias="type", description=ApiDocs.PROPERTY_TYPE_SLUG),
    city: Optional[str] = Query(None, description=ApiDocs.CITY_NAME_LOWERCASE),
    locations: Optional[str] = Query(None, description=ApiDocs.LOCATIONS_CSV_LOWERCASE),
    search: Optional[str] = Query(None, description=ApiDocs.PROPERTY_SEARCH_TEXT),
    lat: Optional[float] = Query(None, description=ApiDocs.PROPERTY_SEARCH_LAT),
    lng: Optional[float] = Query(None, description=ApiDocs.PROPERTY_SEARCH_LNG),
    radius: Optional[float] = Query(
        None,
        ge=0.1,
        le=500,
        description=ApiDocs.PROPERTY_SEARCH_RADIUS_KM,
    ),
    budget_min: Optional[str] = Query(None, alias="budgetMin", description=ApiDocs.BUDGET_MIN_JD_NUMERIC_STRING),
    budget_max: Optional[str] = Query(None, alias="budgetMax", description=ApiDocs.BUDGET_MAX_JD_NUMERIC_STRING),
    min_price: Optional[str] = Query(None, alias="minPrice", description=ApiDocs.MIN_PRICE_ALIAS),
    max_price: Optional[str] = Query(None, alias="maxPrice", description=ApiDocs.MAX_PRICE_ALIAS),
    page: int = Query(1, ge=1, description=ApiDocs.PAGE_NUMBER_1_BASED),
    page_size: int = Query(12, alias="pageSize", ge=1, le=100, description=ApiDocs.ITEMS_PER_PAGE),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
    """Build property search params for exclusive listings only (exclusive=true).

    Returns:
        PropertySearchParams with exclusive fixed to "true".
    """
    return _build_property_search_params(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        search=search,
        lat=lat,
        lng=lng,
        radius=radius,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        exclusive="true",
        page=page,
        page_size=page_size,
        lang=lang,
    )


@router.get("")
def list_properties(
    params: Annotated[PropertySearchParams, Depends(get_property_search_params)],
    service: Annotated[PropertySearchService, Depends(get_property_search_service)],
) -> StandardResponse[PropertySearchResponse]:
    """Search properties with optional filters and pagination."""
    result = service.search(params)
    meta = calculate_pagination(page=result.page, page_size=result.pageSize, total=result.total)
    return create_success_response(data=result, message=None, pagination=meta)


@router.get("/exclusive")
def list_exclusive_properties(
    params: Annotated[PropertySearchParams, Depends(get_exclusive_property_search_params)],
    service: Annotated[PropertySearchService, Depends(get_property_search_service)],
) -> StandardResponse[PropertySearchResponse]:
    """List exclusive properties with optional filters and pagination."""
    result = service.search(params)
    meta = calculate_pagination(page=result.page, page_size=result.pageSize, total=result.total)
    return create_success_response(data=result, message=None, pagination=meta)


@router.get("/{property_id}/similar")
def get_similar_properties(
    property_id: str,  # FastAPI path params are always strings
    service: Annotated[PropertySearchService, Depends(get_property_search_service)],
    limit: Annotated[int, Query(ge=1, le=50, description=ApiDocs.MAX_SIMILAR_PROPERTIES)] = 20,
    lang: Annotated[Optional[str], Query(description=Defaults.LANG_QUERY_DESCRIPTION)] = None,
) -> StandardResponse[PropertySearchResponse]:
    """Get similar properties for a given property."""
    result = service.get_similar(property_id, limit=limit, lang=lang)
    meta = calculate_pagination(page=result.page, page_size=result.pageSize, total=result.total)
    return create_success_response(data=result, message=None, pagination=meta)


@router.get("/{property_id}")
def get_property(
    property_id: str,  # FastAPI path params are always strings
    service: Annotated[PropertySearchService, Depends(get_property_search_service)],
    recent_view_service: Annotated[RecentViewService, Depends(get_recent_view_service)],
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)],
    lang: Annotated[Optional[str], Query(description=Defaults.LANG_QUERY_DESCRIPTION)] = None,
) -> StandardResponse[PropertyDetail]:
    """Get detailed property data and auto-track recent view for logged-in users."""
    detail, prop = service.get_detail_with_entity(property_id, lang=lang)

    # Non-blocking tracking: property detail response must not fail if tracking fails.
    if current_user is not None:
        try:
            recent_view_service.add_or_refresh(
                user_id=current_user.id,
                property_id=prop.id,
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            api_logger.warning("Failed to track recent view for user %s: %s", current_user.id, exc)

    return create_success_response(data=detail, message=None)
