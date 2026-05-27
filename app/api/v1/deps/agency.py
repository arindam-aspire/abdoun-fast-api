"""Dependency providers for agency routes."""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.agency_repository import AgencyRepository
from app.services.agency_service import AgencyService
from app.services.s3_service import S3Service


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_agency_repository(db: DBSessionDep) -> AgencyRepository:
    return AgencyRepository(db)


def get_agency_service(repo: AgencyRepository = Depends(get_agency_repository)) -> AgencyService:
    return AgencyService(repo, s3_service=S3Service())
