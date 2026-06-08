"""Shared email/phone OTP challenge flow for user and agency contact updates."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.models.user_profile_change_challenge import UserProfileChangeChallenge
from app.repositories.profile_change_repository import ProfileChangeRepository
from app.schemas.user import (
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
    """Stored in ``UserProfileChangeChallenge.purpose``."""

    EMAIL = "email"
    PHONE = "phone"
    AGENCY_EMAIL = "agency_email"
    AGENCY_PHONE = "agency_phone"


def random_otp_digits(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(code: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{code}".encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def session_placeholder_hash(session: str) -> str:
    """Placeholder for otp_hash when Cognito CUSTOM_AUTH carries the real OTP."""
    return hashlib.sha256(f"cognito_session:{session}".encode("utf-8")).hexdigest()


def http_exception_for_login_otp_request_error(exc: ClientError) -> HTTPException:
    """Map Cognito initiate_auth (CUSTOM_AUTH) errors like ``AuthService.login_otp_request``."""
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


@dataclass(frozen=True)
class ContactSnapshot:
    """Current contact values used for change detection and Cognito OTP delivery."""

    email: str
    phone: Optional[str]


@dataclass(frozen=True)
class ContactChangePurposes:
    email: str
    phone: str


DuplicateCheck = Callable[[str], Optional[str]]


def request_email_phone_otp(
    *,
    challenge_repo: ProfileChangeRepository,
    actor_user_id: UUID,
    cognito_otp_username: str,
    current: ContactSnapshot,
    new_email: Optional[str],
    new_phone: Optional[str],
    purposes: ContactChangePurposes,
    email_in_use: DuplicateCheck,
    phone_in_use: DuplicateCheck,
    settings: Settings | None = None,
    return_otp_in_response: bool = False,
) -> ProfileUpdateRequestResponse:
    """Create OTP challenges for email and/or phone when values differ from ``current``."""
    settings = settings or get_settings()
    verification_fields: List[str] = []
    dev_phone_otp: Optional[str] = None
    dev_email_otp: Optional[str] = None

    normalized_new_email = normalize_email(str(new_email)) if new_email is not None else None
    no_email = new_email is None or normalized_new_email == normalize_email(current.email)
    no_phone = (
        new_phone is None
        or (current.phone is not None and current.phone == new_phone)
    )

    if no_email and no_phone:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.PROFILE_UPDATE_NO_CHANGES,
        )

    try:
        if not no_email:
            assert normalized_new_email is not None
            conflict = email_in_use(normalized_new_email)
            if conflict:
                raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=conflict)
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=settings.profile_otp_ttl_minutes
            )
            challenge_repo.delete_for_user_purpose(user_id=actor_user_id, purpose=purposes.email)

            if return_otp_in_response:
                email_code = random_otp_digits()
                challenge_repo.create_challenge(
                    user_id=actor_user_id,
                    purpose=purposes.email,
                    new_value=normalized_new_email,
                    otp_hash=hash_otp(email_code, settings.profile_otp_pepper),
                    expires_at=expires_at,
                )
                dev_email_otp = email_code
            else:
                try:
                    auth_response = cognito_service.login_otp_request(cognito_otp_username)
                except ClientError as e:
                    raise http_exception_for_login_otp_request_error(e) from e
                except Exception as e:
                    api_logger.error(
                        format_log_message(
                            LogMessages.Auth.OTP_REQUEST_FAILED,
                            username=cognito_otp_username,
                            error=str(e),
                        )
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
                challenge_parameters = auth_response.get("ChallengeParameters") or {}
                cognito_otp = challenge_parameters.get("otp")
                if cognito_otp:
                    dev_email_otp = str(cognito_otp)
                challenge_repo.create_challenge(
                    user_id=actor_user_id,
                    purpose=purposes.email,
                    new_value=normalized_new_email,
                    otp_hash=session_placeholder_hash(session),
                    expires_at=expires_at,
                    cognito_custom_auth_session=session,
                )
            verification_fields.append("email")

        if not no_phone:
            assert new_phone is not None
            conflict = phone_in_use(new_phone)
            if conflict:
                raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=conflict)
            code = random_otp_digits()
            otp_hash = hash_otp(code, settings.profile_otp_pepper)
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=settings.profile_otp_ttl_minutes
            )
            challenge_repo.delete_for_user_purpose(user_id=actor_user_id, purpose=purposes.phone)
            challenge_repo.create_challenge(
                user_id=actor_user_id,
                purpose=purposes.phone,
                new_value=new_phone,
                otp_hash=otp_hash,
                expires_at=expires_at,
            )
            verification_fields.append("phone_number")
            if return_otp_in_response or not settings.profile_otp_hide_phone_code_in_response:
                dev_phone_otp = code

        if verification_fields:
            challenge_repo.commit()

    except HTTPException:
        challenge_repo.rollback()
        raise
    except Exception as exc:
        challenge_repo.rollback()
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
            dev_email_otp=dev_email_otp,
            otp=dev_email_otp or dev_phone_otp,
        )
    return ProfileUpdateRequestResponse(
        message=SuccessMessages.PROFILE_UPDATED_SUCCESS,
        requires_verification=False,
        verification_fields=[],
        dev_phone_otp=None,
        dev_email_otp=None,
        otp=None,
    )


def verify_email_phone_otp(
    *,
    challenge_repo: ProfileChangeRepository,
    actor_user_id: UUID,
    cognito_otp_username: str,
    body: ProfileUpdateVerifyRequest,
    purposes: ContactChangePurposes,
    email_in_use: DuplicateCheck,
    phone_in_use: DuplicateCheck,
    on_verified_email: Callable[[str], None],
    on_verified_phone: Callable[[str], None],
    cognito_username_for_admin: str,
    cognito_sub: Optional[str],
    settings: Settings | None = None,
) -> ProfileUpdateVerifyResponse:
    """Verify OTP challenges and invoke callbacks to persist email/phone changes."""
    settings = settings or get_settings()

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

    email_challenge: Optional[UserProfileChangeChallenge] = None
    phone_challenge: Optional[UserProfileChangeChallenge] = None
    normalized_email: Optional[str] = None
    normalized_phone: Optional[str] = None

    if do_email:
        normalized_email = normalize_email(str(body.email))
        email_otp = body.email_otp
        assert email_otp is not None
        email_challenge = challenge_repo.get_valid_challenge(
            user_id=actor_user_id,
            purpose=purposes.email,
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
                    cognito_otp_username,
                    email_otp.strip(),
                )
            except (ClientError, Exception) as e:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_OTP,
                ) from e
        elif email_challenge.otp_hash != hash_otp(email_otp.strip(), settings.profile_otp_pepper):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_OTP,
            )
        conflict = email_in_use(normalized_email)
        if conflict:
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=conflict)

    if do_phone:
        normalized_phone = body.phone_number
        assert normalized_phone is not None
        phone_otp = body.phone_otp
        assert phone_otp is not None
        phone_challenge = challenge_repo.get_valid_challenge(
            user_id=actor_user_id,
            purpose=purposes.phone,
            new_value=normalized_phone,
        )
        if (
            not phone_challenge
            or phone_challenge.otp_hash != hash_otp(phone_otp.strip(), settings.profile_otp_pepper)
        ):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_OTP,
            )
        conflict = phone_in_use(normalized_phone)
        if conflict:
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=conflict)

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
        if cognito_attrs and cognito_sub and settings.cognito_user_pool_id:
            cognito_service.admin_update_user_attributes(
                username=cognito_username_for_admin,
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
        assert normalized_email is not None
        on_verified_email(normalized_email)
        challenge_repo.delete_challenge(email_challenge)
    if do_phone:
        assert normalized_phone is not None
        on_verified_phone(normalized_phone)
        challenge_repo.delete_challenge(phone_challenge)

    try:
        challenge_repo.commit()
    except Exception as exc:
        challenge_repo.rollback()
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.REGISTRATION_FAILED,
        ) from exc

    return ProfileUpdateVerifyResponse(message=SuccessMessages.PROFILE_UPDATED_SUCCESS)
