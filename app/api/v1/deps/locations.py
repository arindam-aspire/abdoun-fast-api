from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.location_repository import LocationRepository
from app.services.location_service import LocationService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_location_repository(db: DBSessionDep) -> LocationRepository:
    """FastAPI dependency that provides a LocationRepository instance."""
    return LocationRepository(db)


def get_location_service(
    repo: LocationRepository = Depends(get_location_repository),
) -> LocationService:
    """FastAPI dependency that provides a LocationService instance."""
    return LocationService(repo)

