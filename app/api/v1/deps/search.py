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
    """Provide a PropertyRepository for geo-search and import flows.

    Args:
        db: Injected database session (from get_db).

    Returns:
        PropertyRepository instance.
    """
    return PropertyRepository(db)


def get_geo_search_service(
    repo: PropertyRepository = Depends(get_search_property_repository),
) -> GeoSearchService:
    """Provide a GeoSearchService for POST /properties/geo-search.

    Args:
        repo: Injected PropertyRepository (from get_search_property_repository).

    Returns:
        GeoSearchService instance.
    """
    return GeoSearchService(repo)


def get_property_import_service(db: DBSessionDep) -> PropertyImportService:
    """Provide a PropertyImportService for POST /properties/import-csv.

    Args:
        db: Injected database session (from get_db).

    Returns:
        PropertyImportService instance.
    """
    return PropertyImportService(db)
