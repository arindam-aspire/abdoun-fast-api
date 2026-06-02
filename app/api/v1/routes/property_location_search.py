"""Location autocomplete and geo property search."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps.property_location_search import (
    get_location_autocomplete_service,
    get_property_location_search_service,
)
from app.core.limiter import limiter
from app.domains.shared.pagination import calculate_pagination
from app.schemas.property_location_search import (
    LocationAutocompleteResponse,
    PropertyLocationSearchResponse,
)
from app.services.location_autocomplete_service import LocationAutocompleteService
from app.services.property_location_search_service import PropertyLocationSearchService
from app.utils.constants import ApiDocs, Defaults, RateLimits
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get("/autocomplete")
@limiter.limit(RateLimits.SEARCH_AUTOCOMPLETE)
def location_autocomplete(
    request: Request,
    q: Annotated[str, Query(min_length=0, description="Search text (min 2 chars)")],
    service: Annotated[LocationAutocompleteService, Depends(get_location_autocomplete_service)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> StandardResponse[LocationAutocompleteResponse]:
    """Suggest locations from local cities/areas and OpenStreetMap Nominatim."""
    return service.autocomplete(q, limit=limit)


@router.get("/properties")
@limiter.limit(RateLimits.SEARCH_PROPERTIES)
def search_properties_with_location(
    request: Request,
    service: Annotated[PropertyLocationSearchService, Depends(get_property_location_search_service)],
    search: Annotated[Optional[str], Query(description="Location or area text (highest priority)")] = None,
    lat: Annotated[Optional[float], Query(description="Latitude (GPS or geocoded)")] = None,
    lng: Annotated[Optional[float], Query(description="Longitude (GPS or geocoded)")] = None,
    radius: Annotated[Optional[float], Query(ge=0.1, le=500, description="Radius in km")] = None,
    status: Annotated[Optional[str], Query(description=ApiDocs.LISTING_TYPE_BUY_RENT)] = None,
    category: Annotated[Optional[str], Query(description=ApiDocs.PROPERTY_CATEGORY)] = None,
    type_slug: Annotated[Optional[str], Query(alias="type", description=ApiDocs.PROPERTY_TYPE_SLUG)] = None,
    exclusive: Annotated[Optional[str], Query(description=ApiDocs.EXCLUSIVE_FILTER)] = None,
    budget_min: Annotated[Optional[str], Query(alias="budgetMin")] = None,
    budget_max: Annotated[Optional[str], Query(alias="budgetMax")] = None,
    min_price: Annotated[Optional[str], Query(alias="minPrice")] = None,
    max_price: Annotated[Optional[str], Query(alias="maxPrice")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
    lang: Annotated[Optional[str], Query(description=Defaults.LANG_QUERY_DESCRIPTION)] = None,
) -> StandardResponse[PropertyLocationSearchResponse]:
    """
    Search properties by text and/or geo (PostgreSQL + Haversine).

    Rules:
    - ``search`` text is geocoded and overrides GPS for the distance filter center.
    - GPS (``lat``/``lng``) is used when no search text is provided (e.g. Near Me).
    """
    response = service.search(
        search=search,
        lat=lat,
        lng=lng,
        radius=radius,
        status=status,
        category=category,
        type_slug=type_slug,
        exclusive=exclusive,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        page=page,
        page_size=page_size,
        lang=lang,
    )
    meta = calculate_pagination(
        page=response.data.page,
        page_size=response.data.pageSize,
        total=response.data.total,
    )
    return create_success_response(data=response.data, message=None, pagination=meta)
