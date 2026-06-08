"""Self-service profile updates: unified request/verify (name immediate; email/phone OTP)."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from app.models.user import User
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
from app.utils.constants import ErrorMessages, SuccessMessages
from app.utils.status_codes import HTTPStatus

# Re-export for tests that import _hash_otp from this module.
from app.services.profile_contact_otp import hash_otp as _hash_otp  # noqa: F401


class ProfileUpdateService:
    """Authenticated user profile mutations without admin RBAC permissions."""

    def __init__(
        self,
        auth_repo: AuthRepository,
        challenge_repo: ProfileChangeRepository,
    ) -> None:
        self._auth = auth_repo
        self._challenges = challenge_repo

    def request_profile_update(
        self,
        *,
        current_user: User,
        body: ProfileUpdateRequest,
    ) -> ProfileUpdateRequestResponse:
        """Apply immediate name changes and/or create OTP challenges for email/phone."""
        if body.full_name is None and body.email is None and body.phone_number is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_UPDATE_NO_FIELDS,
            )

        new_email = normalize_email(str(body.email)) if body.email is not None else None
        new_phone = body.phone_number

        no_name = body.full_name is None or body.full_name.strip() == current_user.full_name
        no_email = body.email is None or new_email == normalize_email(current_user.email)
        no_phone = (
            body.phone_number is None
            or (
                current_user.phone_number is not None
                and current_user.phone_number == new_phone
            )
        )
        if no_name and no_email and no_phone:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_UPDATE_NO_CHANGES,
            )

        if body.full_name is not None and not no_name:
            name = body.full_name.strip()
            if not name:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.PROFILE_NAME_INVALID,
                )
            current_user.full_name = name
            try:
                self._auth.commit()
                self._auth.refresh(current_user)
            except Exception:
                self._auth.rollback()
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.REGISTRATION_FAILED,
                )

        if no_email and no_phone:
            return ProfileUpdateRequestResponse(
                message=SuccessMessages.PROFILE_UPDATED_SUCCESS,
                requires_verification=False,
                verification_fields=[],
                dev_phone_otp=None,
                dev_email_otp=None,
                otp=None,
            )

        user_id = current_user.id

        def email_in_use(email: str) -> Optional[str]:
            if self._auth.user_exists_by_email_excluding(
                email=email, exclude_user_id=user_id
            ):
                return ErrorMessages.PROFILE_EMAIL_IN_USE
            return None

        def phone_in_use(phone: str) -> Optional[str]:
            if self._auth.user_exists_by_phone_excluding(
                phone=phone, exclude_user_id=user_id
            ):
                return ErrorMessages.PROFILE_PHONE_IN_USE
            return None

        return request_email_phone_otp(
            challenge_repo=self._challenges,
            actor_user_id=user_id,
            cognito_otp_username=current_user.email,
            current=ContactSnapshot(
                email=current_user.email,
                phone=current_user.phone_number,
            ),
            new_email=body.email and str(body.email) or None,
            new_phone=body.phone_number,
            purposes=ContactChangePurposes(
                email=ProfileChangePurpose.EMAIL,
                phone=ProfileChangePurpose.PHONE,
            ),
            email_in_use=email_in_use,
            phone_in_use=phone_in_use,
        )

    def verify_profile_update(
        self,
        *,
        current_user: User,
        body: ProfileUpdateVerifyRequest,
    ) -> ProfileUpdateVerifyResponse:
        """Apply verified email and/or phone updates from OTP challenges."""
        user_id = current_user.id

        def email_in_use(email: str) -> Optional[str]:
            if self._auth.user_exists_by_email_excluding(
                email=email, exclude_user_id=user_id
            ):
                return ErrorMessages.PROFILE_EMAIL_IN_USE
            return None

        def phone_in_use(phone: str) -> Optional[str]:
            if self._auth.user_exists_by_phone_excluding(
                phone=phone, exclude_user_id=user_id
            ):
                return ErrorMessages.PROFILE_PHONE_IN_USE
            return None

        def on_email(value: str) -> None:
            current_user.email = value
            current_user.is_email_verified = True

        def on_phone(value: str) -> None:
            current_user.phone_number = value
            current_user.is_phone_verified = True

        result = verify_email_phone_otp(
            challenge_repo=self._challenges,
            actor_user_id=user_id,
            cognito_otp_username=current_user.email,
            body=body,
            purposes=ContactChangePurposes(
                email=ProfileChangePurpose.EMAIL,
                phone=ProfileChangePurpose.PHONE,
            ),
            email_in_use=email_in_use,
            phone_in_use=phone_in_use,
            on_verified_email=on_email,
            on_verified_phone=on_phone,
            cognito_username_for_admin=current_user.email,
            cognito_sub=current_user.cognito_sub,
        )
        self._auth.refresh(current_user)
        return result
