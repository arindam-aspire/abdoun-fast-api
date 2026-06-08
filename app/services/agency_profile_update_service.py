"""Agency email/phone updates via the same OTP request/verify flow as user profile contact changes."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException

from app.models.agency import Agency
from app.models.user import User
from app.repositories.agency_repository import AgencyRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.profile_change_repository import ProfileChangeRepository
from app.schemas.user import (
    ProfileUpdateRequest,
    ProfileUpdateRequestResponse,
    ProfileUpdateVerifyRequest,
    ProfileUpdateVerifyResponse,
)
from app.services.profile_contact_otp import (
    ContactChangePurposes,
    ContactSnapshot,
    ProfileChangePurpose,
    normalize_email,
    request_email_phone_otp,
    verify_email_phone_otp,
)
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.status_codes import HTTPStatus


class AgencyProfileUpdateService:
    """OTP-gated agency contact updates; challenges are keyed by the acting admin's user id."""

    def __init__(
        self,
        agency_repo: AgencyRepository,
        auth_repo: AuthRepository,
        challenge_repo: ProfileChangeRepository,
    ) -> None:
        self._agency = agency_repo
        self._auth = auth_repo
        self._challenges = challenge_repo

    def _assert_can_manage_agency(self, *, current_user: User, agency_id: uuid.UUID) -> Agency:
        roles = {role.name for role in current_user.roles}
        if UserRoles.SUPER_ADMIN in roles:
            pass
        elif UserRoles.ADMIN in roles and (
            current_user.agency_id is None or current_user.agency_id == agency_id
        ):
            pass
        else:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.AGENCY_ACCESS_DENIED,
            )
        agency = self._agency.get_by_id(agency_id)
        if not agency:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENCY_NOT_FOUND,
            )
        return agency

    def _email_in_use(
        self, *, email: str, agency_id: uuid.UUID, exclude_user_id: uuid.UUID
    ) -> Optional[str]:
        if self._agency.agency_email_exists_excluding(email=email, exclude_agency_id=agency_id):
            return ErrorMessages.AGENCY_EXISTS
        if self._auth.user_exists_by_email_excluding(
            email=email, exclude_user_id=exclude_user_id
        ):
            return ErrorMessages.PROFILE_EMAIL_IN_USE
        return None

    def _phone_in_use(
        self, *, phone: str, agency_id: uuid.UUID, exclude_user_id: uuid.UUID
    ) -> Optional[str]:
        if self._agency.agency_phone_exists_excluding(phone=phone, exclude_agency_id=agency_id):
            return ErrorMessages.AGENCY_EXISTS
        if self._auth.user_exists_by_phone_excluding(
            phone=phone, exclude_user_id=exclude_user_id
        ):
            return ErrorMessages.PROFILE_PHONE_IN_USE
        return None

    def request_agency_contact_update(
        self,
        *,
        agency_id: uuid.UUID,
        current_user: User,
        body: ProfileUpdateRequest,
    ) -> ProfileUpdateRequestResponse:
        """Create OTP challenges for agency email and/or phone changes."""
        if body.email is None and body.phone_number is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_UPDATE_NO_FIELDS,
            )

        agency = self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        user_id = current_user.id

        def email_in_use(email: str) -> Optional[str]:
            return self._email_in_use(
                email=email, agency_id=agency.id, exclude_user_id=user_id
            )

        def phone_in_use(phone: str) -> Optional[str]:
            return self._phone_in_use(
                phone=phone, agency_id=agency.id, exclude_user_id=user_id
            )

        return request_email_phone_otp(
            challenge_repo=self._challenges,
            actor_user_id=user_id,
            cognito_otp_username=current_user.email,
            current=ContactSnapshot(email=agency.email, phone=agency.phone),
            new_email=body.email and str(body.email) or None,
            new_phone=body.phone_number,
            purposes=ContactChangePurposes(
                email=ProfileChangePurpose.AGENCY_EMAIL,
                phone=ProfileChangePurpose.AGENCY_PHONE,
            ),
            email_in_use=email_in_use,
            phone_in_use=phone_in_use,
            return_otp_in_response=True,
        )

    def verify_agency_contact_update(
        self,
        *,
        agency_id: uuid.UUID,
        current_user: User,
        body: ProfileUpdateVerifyRequest,
    ) -> ProfileUpdateVerifyResponse:
        """Verify OTP(s) and persist agency + linked user contact fields."""
        agency = self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        user_id = current_user.id
        old_email = agency.email
        old_phone = agency.phone

        def email_in_use(email: str) -> Optional[str]:
            return self._email_in_use(
                email=email, agency_id=agency.id, exclude_user_id=user_id
            )

        def phone_in_use(phone: str) -> Optional[str]:
            return self._phone_in_use(
                phone=phone, agency_id=agency.id, exclude_user_id=user_id
            )

        def on_email(value: str) -> None:
            agency.email = value
            for user in self._agency.list_users_by_agency_id(agency.id):
                if normalize_email(user.email) == normalize_email(old_email):
                    user.email = value
                    user.is_email_verified = True

        def on_phone(value: str) -> None:
            agency.phone = value
            for user in self._agency.list_users_by_agency_id(agency.id):
                if user.phone_number == old_phone:
                    user.phone_number = value
                    user.is_phone_verified = True

        cognito_username = current_user.email
        result = verify_email_phone_otp(
            challenge_repo=self._challenges,
            actor_user_id=user_id,
            cognito_otp_username=current_user.email,
            body=body,
            purposes=ContactChangePurposes(
                email=ProfileChangePurpose.AGENCY_EMAIL,
                phone=ProfileChangePurpose.AGENCY_PHONE,
            ),
            email_in_use=email_in_use,
            phone_in_use=phone_in_use,
            on_verified_email=on_email,
            on_verified_phone=on_phone,
            cognito_username_for_admin=cognito_username,
            cognito_sub=current_user.cognito_sub,
        )
        self._agency.refresh(agency)
        return result
