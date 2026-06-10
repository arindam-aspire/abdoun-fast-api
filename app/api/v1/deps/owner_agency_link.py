"""Dependency providers for owner agency linking routes."""

from fastapi import Depends

from app.api.v1.deps.agency import get_agency_repository
from app.api.v1.deps.users import get_user_repository
from app.repositories.agency_repository import AgencyRepository
from app.repositories.user_repository import UserRepository
from app.services.owner_agency_link_service import OwnerAgencyLinkService


def get_owner_agency_link_service(
    user_repo: UserRepository = Depends(get_user_repository),
    agency_repo: AgencyRepository = Depends(get_agency_repository),
) -> OwnerAgencyLinkService:
    """Provide OwnerAgencyLinkService for PATCH /users/agency."""
    return OwnerAgencyLinkService(user_repo, agency_repo)
