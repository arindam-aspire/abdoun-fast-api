from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.property import (
    PropertySearchRequest,
    PropertyListResponse,
)
from app.services.csv_importer import import_properties_from_csv_file
from app.utils.status_codes import STATUS_CREATED
from app.utils.responses import ImportResponse

router = APIRouter()

DBSessionDep = Annotated[Session, Depends(get_db)]


@router.post("/geo-search", response_model=PropertyListResponse)
def search_properties(
    payload: PropertySearchRequest,
    db: DBSessionDep,
) -> PropertyListResponse:
    items = payload.execute(db)
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








