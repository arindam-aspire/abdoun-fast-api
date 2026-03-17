"""Dependencies for search and import routes (geo-search, import-csv)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_repository import PropertyRepository
from app.services.geo_search_service import GeoSearchService
from app.services.property_import_service import PropertyImportService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_search_property_repository(db: DBSessionDep) -> PropertyRepository:
    """PropertyRepository for geo-search (no DB in router)."""
    return PropertyRepository(db)


def get_geo_search_service(
    repo: PropertyRepository = Depends(get_search_property_repository),
) -> GeoSearchService:
    """GeoSearchService for POST /geo-search."""
    return GeoSearchService(repo)


def get_property_import_service(db: DBSessionDep) -> PropertyImportService:
    """PropertyImportService for POST /import-csv."""
    return PropertyImportService(db)
