"""Self-service profile updates: unified request/verify (name immediate; email/phone OTP)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.user import User
from app.models.user_profile_change_challenge import UserProfileChangeChallenge
from app.repositories.auth_repository import AuthRepository
from app.repositories.profile_change_repository import ProfileChangeRepository
from app.schemas.user import (
    ProfileUpdateRequest,
    ProfileUpdateRequestResponse,
    ProfileUpdateVerifyRequest,
    ProfileUpdateVerifyResponse,
)
from app.services.cognito import cognito_service
from app.utils.constants import CognitoConstants, ErrorMessages, SuccessMessages
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.status_codes import HTTPStatus


class ProfileChangePurpose:
    """Stored in `UserProfileChangeChallenge.purpose`."""

    EMAIL = "email"
    PHONE = "phone"


def _random_otp_digits(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _hash_otp(code: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{code}".encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _session_placeholder_hash(session: str) -> str:
    """Deterministic placeholder for otp_hash when Cognito CUSTOM_AUTH carries the real OTP."""
    return hashlib.sha256(f"cognito_session:{session}".encode("utf-8")).hexdigest()


def _http_exception_for_login_otp_request_error(exc: ClientError) -> HTTPException:
    """Map Cognito initiate_auth (CUSTOM_AUTH) errors like `AuthService.login_otp_request`."""
    error_code = exc.response["Error"]["Code"]
    error_msg = (exc.response.get("Error") or {}).get("Message", str(exc))
    if error_code == "UserNotFoundException":
        return HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.USER_NOT_FOUND,
        )
    if error_code == "InvalidParameterException" and CognitoConstants.OTP_ERROR_SUBSTRING in error_msg:
        return HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.OTP_NOT_CONFIGURED,
        )
    server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(exc))
    return HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail=server_error,
    )


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

        settings = get_settings()
        verification_fields: List[str] = []
        dev_phone_otp: Optional[str] = None

        new_email = _normalize_email(str(body.email)) if body.email is not None else None
        new_phone = body.phone_number

        no_name = body.full_name is None or body.full_name.strip() == current_user.full_name
        no_email = body.email is None or new_email == _normalize_email(current_user.email)
        no_phone = (
            body.phone_number is None
            or (current_user.phone_number is not None and current_user.phone_number == new_phone)
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

        try:
            if not no_email:
                if self._auth.user_exists_by_email_excluding(
                    email=new_email, exclude_user_id=current_user.id
                ):
                    raise HTTPException(
                        status_code=HTTPStatus.CONFLICT,
                        detail=ErrorMessages.PROFILE_EMAIL_IN_USE,
                    )
                # Same delivery path as POST /auth/login/otp/request: Cognito CUSTOM_AUTH + Lambda (SES/SMS).
                # Code is sent to the user's current pool attributes (same as login), not directly to new_email.
                try:
                    auth_response = cognito_service.login_otp_request(current_user.email)
                except ClientError as e:
                    raise _http_exception_for_login_otp_request_error(e) from e
                except Exception as e:
                    api_logger.error(
                        format_log_message(LogMessages.Auth.OTP_REQUEST_FAILED, username=current_user.email, error=str(e))
                    )
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e)),
                    ) from e

                session = auth_response.get("Session")
                if not session:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=ErrorMessages.OTP_NOT_CONFIGURED,
                    )
                expires_at = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.profile_otp_ttl_minutes
                )
                self._challenges.delete_for_user_purpose(
                    user_id=current_user.id, purpose=ProfileChangePurpose.EMAIL
                )
                self._challenges.create_challenge(
                    user_id=current_user.id,
                    purpose=ProfileChangePurpose.EMAIL,
                    new_value=new_email,
                    otp_hash=_session_placeholder_hash(session),
                    expires_at=expires_at,
                    cognito_custom_auth_session=session,
                )
                verification_fields.append("email")

            if not no_phone:
                if self._auth.user_exists_by_phone_excluding(
                    phone=new_phone, exclude_user_id=current_user.id
                ):
                    raise HTTPException(
                        status_code=HTTPStatus.CONFLICT,
                        detail=ErrorMessages.PROFILE_PHONE_IN_USE,
                    )
                code = _random_otp_digits()
                otp_hash = _hash_otp(code, settings.profile_otp_pepper)
                expires_at = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.profile_otp_ttl_minutes
                )
                self._challenges.delete_for_user_purpose(
                    user_id=current_user.id, purpose=ProfileChangePurpose.PHONE
                )
                self._challenges.create_challenge(
                    user_id=current_user.id,
                    purpose=ProfileChangePurpose.PHONE,
                    new_value=new_phone,
                    otp_hash=otp_hash,
                    expires_at=expires_at,
                )
                verification_fields.append("phone_number")
                # SMS is not integrated; clients need the code in the API until outbound SMS exists.
                if not settings.profile_otp_hide_phone_code_in_response:
                    dev_phone_otp = code

            if verification_fields:
                self._challenges.commit()

        except HTTPException:
            self._challenges.rollback()
            raise
        except Exception as exc:
            self._challenges.rollback()
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REGISTRATION_FAILED,
            ) from exc

        if verification_fields:
            return ProfileUpdateRequestResponse(
                message=SuccessMessages.PROFILE_VERIFICATION_REQUIRED,
                requires_verification=True,
                verification_fields=verification_fields,
                dev_phone_otp=dev_phone_otp,
            )
        return ProfileUpdateRequestResponse(
            message=SuccessMessages.PROFILE_UPDATED_SUCCESS,
            requires_verification=False,
            verification_fields=[],
            dev_phone_otp=None,
        )

    def verify_profile_update(
        self,
        *,
        current_user: User,
        body: ProfileUpdateVerifyRequest,
    ) -> ProfileUpdateVerifyResponse:
        """Apply verified email and/or phone updates from OTP challenges."""
        settings = get_settings()
        if body.email_otp is not None and body.email is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_VERIFY_EMAIL_REQUIRED,
            )
        if body.phone_otp is not None and body.phone_number is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_VERIFY_PHONE_REQUIRED,
            )

        do_email = body.email is not None
        do_phone = body.phone_number is not None
        if not do_email and not do_phone:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_VERIFY_NO_PAIRS,
            )
        if do_email and body.email_otp is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_VERIFY_EMAIL_OTP_REQUIRED,
            )
        if do_phone and body.phone_otp is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_VERIFY_PHONE_OTP_REQUIRED,
            )

        old_cognito_username = current_user.email
        email_challenge: Optional[UserProfileChangeChallenge] = None
        phone_challenge: Optional[UserProfileChangeChallenge] = None
        normalized_email: Optional[str] = None
        normalized_phone: Optional[str] = None

        if do_email:
            normalized_email = _normalize_email(str(body.email))
            email_otp = body.email_otp
            assert email_otp is not None
            email_challenge = self._challenges.get_valid_challenge(
                user_id=current_user.id,
                purpose=ProfileChangePurpose.EMAIL,
                new_value=normalized_email,
            )
            if not email_challenge:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_OTP,
                )
            if email_challenge.cognito_custom_auth_session:
                try:
                    cognito_service.login_otp_verify(
                        email_challenge.cognito_custom_auth_session,
                        current_user.email,
                        email_otp.strip(),
                    )
                except ClientError as e:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=ErrorMessages.INVALID_OTP,
                    ) from e
                except Exception as e:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=ErrorMessages.INVALID_OTP,
                    ) from e
            elif email_challenge.otp_hash != _hash_otp(email_otp.strip(), settings.profile_otp_pepper):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_OTP,
                )
            if self._auth.user_exists_by_email_excluding(
                email=normalized_email, exclude_user_id=current_user.id
            ):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ErrorMessages.PROFILE_EMAIL_IN_USE,
                )

        if do_phone:
            normalized_phone = body.phone_number
            assert normalized_phone is not None
            phone_otp = body.phone_otp
            assert phone_otp is not None
            phone_challenge = self._challenges.get_valid_challenge(
                user_id=current_user.id,
                purpose=ProfileChangePurpose.PHONE,
                new_value=normalized_phone,
            )
            if (
                not phone_challenge
                or phone_challenge.otp_hash
                != _hash_otp(phone_otp.strip(), settings.profile_otp_pepper)
            ):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_OTP,
                )
            if self._auth.user_exists_by_phone_excluding(
                phone=normalized_phone, exclude_user_id=current_user.id
            ):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ErrorMessages.PROFILE_PHONE_IN_USE,
                )

        cognito_attrs: List[dict] = []
        if do_email:
            cognito_attrs.extend(
                [
                    {"Name": "email", "Value": normalized_email},
                    {"Name": "email_verified", "Value": "true"},
                ]
            )
        if do_phone:
            cognito_attrs.extend(
                [
                    {"Name": "phone_number", "Value": normalized_phone},
                    {"Name": "phone_number_verified", "Value": "true"},
                ]
            )
        try:
            if cognito_attrs and current_user.cognito_sub and settings.cognito_user_pool_id:
                cognito_service.admin_update_user_attributes(
                    username=old_cognito_username,
                    attributes=cognito_attrs,
                )
        except ClientError as e:
            err = (e.response.get("Error") or {}).get("Code", "")
            if do_email and err in ("UsernameExistsException", "AliasExistsException"):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ErrorMessages.PROFILE_EMAIL_IN_USE,
                ) from e
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.PROFILE_COGNITO_UPDATE_FAILED,
            ) from e

        if do_email:
            current_user.email = normalized_email
            current_user.is_email_verified = True
            self._challenges.delete_challenge(email_challenge)
        if do_phone:
            current_user.phone_number = normalized_phone
            current_user.is_phone_verified = True
            self._challenges.delete_challenge(phone_challenge)

        try:
            self._challenges.commit()
            self._auth.refresh(current_user)
        except Exception as exc:
            self._challenges.rollback()
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REGISTRATION_FAILED,
            ) from exc

        return ProfileUpdateVerifyResponse(
            message=SuccessMessages.PROFILE_UPDATED_SUCCESS,
        )
