"""Link an existing agency to an authenticated owner user account."""
from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.models.agency import Agency
from app.models.user import User
from app.repositories.agency_repository import AgencyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.agency import AgencyResponse
from app.utils.constants import ErrorMessages, SuccessMessages
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus


class OwnerAgencyLinkService:
    """Business logic for PATCH /users/agency (owner-only agency linking)."""

    def __init__(
        self,
        user_repository: UserRepository,
        agency_repository: AgencyRepository,
    ) -> None:
        self._user_repo = user_repository
        self._agency_repo = agency_repository

    def _to_agency_response(self, agency: Agency) -> AgencyResponse:
        picture_map = self._agency_repo.get_profile_picture_map_for_agencies([agency.id])
        data = AgencyResponse.model_validate(agency)
        if picture_map:
            data.profile_picture_url = picture_map.get(agency.id, "") or ""
        return data

    def link_agency(
        self,
        *,
        current_user: User,
        agency_id: uuid.UUID,
    ) -> StandardResponse[AgencyResponse]:
        """Link ``agency_id`` to the owner when not already linked; idempotent when linked."""
        if current_user.agency_id is not None:
            existing_agency = self._agency_repo.get_by_id(current_user.agency_id)
            if existing_agency is not None:
                return create_success_response(
                    data=self._to_agency_response(existing_agency),
                    message=SuccessMessages.AGENCY_ALREADY_LINKED_TO_OWNER,
                )

        agency = self._agency_repo.get_by_id(agency_id)
        if agency is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENCY_NOT_FOUND,
            )

        self._user_repo.set_user_agency_id(user=current_user, agency_id=agency_id)
        self._user_repo.commit()
        self._user_repo.refresh(current_user)
        self._agency_repo.refresh(agency)
        return create_success_response(
            data=self._to_agency_response(agency),
            message=SuccessMessages.AGENCY_LINKED_SUCCESSFULLY,
        )
