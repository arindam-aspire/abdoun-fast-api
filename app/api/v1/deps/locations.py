"""Dependency providers for location routes.

These functions wire repositories/services for `app/api/v1/routes/locations.py`
without performing business logic in the router layer.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.location_repository import LocationRepository
from app.services.location_service import LocationService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_location_repository(db: DBSessionDep) -> LocationRepository:
    """Provide a LocationRepository bound to the request database session.

    Args:
        db: Injected database session (from get_db).

    Returns:
        LocationRepository instance for cities/areas routes.
    """
    return LocationRepository(db)


def get_location_service(
    repo: LocationRepository = Depends(get_location_repository),
) -> LocationService:
    """Provide a LocationService for cities and areas endpoints.

    Args:
        repo: Injected LocationRepository (from get_location_repository).

    Returns:
        LocationService instance.
    """
    return LocationService(repo)

