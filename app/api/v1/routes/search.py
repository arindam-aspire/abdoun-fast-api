from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.property import (
    PropertySearchRequest,
    PropertySearchResult,
    PropertyListResponse,
)
from app.services.csv_importer import import_properties_from_csv_file
from app.services.public_properties import list_public_submissions, serialize_property_listing
from app.utils.status_codes import STATUS_CREATED
from app.utils.responses import ImportResponse

router = APIRouter()

DBSessionDep = Annotated[Session, Depends(get_db)]


@router.post("/search", response_model=PropertyListResponse)
def search_properties(
    payload: PropertySearchRequest,
    db: DBSessionDep,
) -> PropertyListResponse:
    rows = list_public_submissions(db)[: payload.limit]
    items = []
    for submission, submitter in rows:
        listing = serialize_property_listing(db, submission, submitter=submitter)
        try:
            price = float(listing.get("price") or 0)
        except (TypeError, ValueError):
            price = None
        settings = get_settings()
        title = listing.get("title") or {}
        if isinstance(title, dict):
            title_text = title.get("en") or title.get(settings.default_locale)
        else:
            title_text = title
        items.append(
            PropertySearchResult(
                id=int(listing["property_hash_id"]),
                title=title_text or settings.untitled_property_title,
                price=price,
                price_currency=((submission.payload or {}).get("pricing") or {}).get("currency") or settings.default_currency,
                bedrooms=listing.get("bedrooms") or listing.get("beds"),
                bathrooms=listing.get("bathrooms") or listing.get("baths"),
                thumbnail=(listing.get("media") or {}).get("thumbnail"),
                lat=None,
                lng=None,
            )
        )
    return PropertyListResponse(items=items, total=len(items))


@router.post("/import-csv", status_code=STATUS_CREATED, response_model=ImportResponse)
async def import_csv(
    db: DBSessionDep,
    file: UploadFile = File(...),
    geocode_missing: bool = Query(
        False,
        description="If True, geocode locations that don't have coordinates (slower, rate-limited)"
    ),
) -> ImportResponse:
    """
    Import properties from CSV file.
    
    - **geocode_missing**: If True, will geocode locations without coordinates using Nominatim API.
      Note: This is rate-limited to 1 request/second and will significantly slow down the import.
      Recommended: Pre-enrich CSV with coordinates using the enrich_csv_with_coordinates script.
    """
    created_count = await import_properties_from_csv_file(db, file, geocode_missing=geocode_missing)
    return ImportResponse(created=created_count)








