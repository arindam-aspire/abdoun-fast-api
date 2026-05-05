"""Dependency providers for refactored taxonomy routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.taxonomy.repository import TaxonomyRepository
from app.domains.taxonomy.service import TaxonomyService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_taxonomy_repository(db: DBSessionDep) -> TaxonomyRepository:
    return TaxonomyRepository(db)


def get_taxonomy_service(
    repository: TaxonomyRepository = Depends(get_taxonomy_repository),
) -> TaxonomyService:
    return TaxonomyService(repository)

