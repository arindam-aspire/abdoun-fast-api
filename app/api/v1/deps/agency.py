"""Dependency providers for agency routes."""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.agency_repository import AgencyRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.profile_change_repository import ProfileChangeRepository
from app.services.agency_profile_update_service import AgencyProfileUpdateService
from app.services.agency_service import AgencyService
from app.services.s3_service import S3Service


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_agency_repository(db: DBSessionDep) -> AgencyRepository:
    return AgencyRepository(db)


def get_agency_service(repo: AgencyRepository = Depends(get_agency_repository)) -> AgencyService:
    return AgencyService(repo, s3_service=S3Service())


def get_agency_profile_update_service(db: DBSessionDep) -> AgencyProfileUpdateService:
    """OTP contact updates for agencies (reuses profile challenge + auth repositories)."""
    return AgencyProfileUpdateService(
        AgencyRepository(db),
        AuthRepository(db),
        ProfileChangeRepository(db),
    )
