"""Dependency providers for property routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.property_search_service import PropertySearchService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_property_search_service(db: DBSessionDep) -> PropertySearchService:
    """Provide a PropertySearchService for property list/detail/similar endpoints.

    Args:
        db: Injected database session (from get_db).

    Returns:
        PropertySearchService instance.
    """
    return PropertySearchService(db)

