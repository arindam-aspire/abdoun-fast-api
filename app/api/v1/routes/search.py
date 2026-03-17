from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, Query, Request

from app.api.v1.deps.security import get_current_user, require_permission
from app.api.v1.deps.search import get_geo_search_service, get_property_import_service
from app.core.limiter import limiter
from app.models.user import User
from app.schemas.property import PropertySearchRequest, PropertyListResponse
from app.services.geo_search_service import GeoSearchService
from app.services.property_import_service import PropertyImportService
from app.utils.status_codes import STATUS_CREATED
from app.utils.responses import ImportResponse
from app.utils.constants import UserPermissions

router = APIRouter()


@router.post("/geo-search")
@limiter.limit("30/minute")
def search_properties(
    request: Request,
    payload: PropertySearchRequest,
    geo_search_service: Annotated[GeoSearchService, Depends(get_geo_search_service)],
) -> PropertyListResponse:
    return geo_search_service.search(payload)


@router.post(
    "/import-csv",
    status_code=STATUS_CREATED,
    dependencies=[require_permission(UserPermissions.PROPERTY_CREATE)],
)
@limiter.limit("2/minute")
async def import_csv(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
    import_service: Annotated[PropertyImportService, Depends(get_property_import_service)],
    geocode_missing: Annotated[
        bool,
        Query(description="If True, geocode locations that don't have coordinates (slower, rate-limited)"),
    ] = False,
) -> ImportResponse:
    """
    Import properties from CSV file.
    
    - **geocode_missing**: If True, will geocode locations without coordinates using Nominatim API.
      Note: This is rate-limited to 1 request/second and will significantly slow down the import.
      Recommended: Pre-enrich CSV with coordinates using the enrich_csv_with_coordinates script.
    """
    created_count = await import_service.import_from_csv(file, geocode_missing=geocode_missing)
    return ImportResponse(created=created_count)




