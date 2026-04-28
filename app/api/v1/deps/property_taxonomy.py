"""Dependency providers for property taxonomy routes.

These functions wire repositories/services for `app/api/v1/routes/property_taxonomy.py`
without performing business logic in the router layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_taxonomy_repository import PropertyTaxonomyRepository
from app.services.property_taxonomy_service import PropertyTaxonomyService

DBSessionDep = Annotated[Session, Depends(get_db)]


def get_property_taxonomy_repository(db: DBSessionDep) -> PropertyTaxonomyRepository:
    """Provide a PropertyTaxonomyRepository bound to the request database session.

    Args:
        db: Injected database session (from get_db).

    Returns:
        PropertyTaxonomyRepository instance for property taxonomy endpoints.
    """
    return PropertyTaxonomyRepository(db)


def get_property_taxonomy_service(
    repo: PropertyTaxonomyRepository = Depends(get_property_taxonomy_repository),
) -> PropertyTaxonomyService:
    """Provide a PropertyTaxonomyService for property taxonomy endpoints.

    Args:
        repo: Injected PropertyTaxonomyRepository (from get_property_taxonomy_repository).

    Returns:
        PropertyTaxonomyService instance.
    """
    return PropertyTaxonomyService(repo)

