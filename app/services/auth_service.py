"""Auth service: signup, login (password/OTP), refresh, logout, profile, permissions; uses AuthRepository and Cognito."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_remember_me_session_repository import UserRememberMeSessionRepository
from app.schemas.user import (
    ConfirmSignupRequest,
    ForgotPasswordConfirm,
    ForgotPasswordRequest,
    LoginRequest,
    OTPRequest,
    OTPVerify,
    PermissionsResponse,
    RefreshRequest,
    ResendConfirmationRequest,
    SetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.cognito import cognito_service
from app.services.media_url_signer import MediaUrlSigner
from app.services.remember_me_crypto import decrypt_refresh_token, encrypt_refresh_token
from app.services.remember_me_http_effect import RememberMeHttpEffect
from app.utils.auth_access_token import (
    cognito_refresh_username,
    cognito_sub_from_payload,
    create_auth_access_token,
    decode_auth_access_token,
    parse_user_id_from_payload,
)
from app.services.remember_me_tokens import generate_opaque_remember_me_token, hash_remember_me_opaque_token
from app.utils.constants import (
    CognitoConstants,
    Defaults,
    ErrorMessages,
    RememberMeConstants,
    SuccessMessages,
    UserRoles,
)
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus
from app.api.v1.deps.security import get_user_permissions


class AuthService:
    """Service layer encapsulating authentication and user signup flows."""

    def __init__(
        self,
        repository: AuthRepository,
        *,
        media_url_signer: MediaUrlSigner | None = None,
        remember_me_repository: UserRememberMeSessionRepository | None = None,
    ) -> None:
        self._repo = repository
        self._media_url_signer = media_url_signer
        self._remember_me_repo = remember_me_repository or UserRememberMeSessionRepository(
            repository._db
        )

    def _sign_user_response(self, user_response: UserResponse) -> UserResponse:
        if self._media_url_signer is not None:
            self._media_url_signer.apply_user_response(user_response)
        return user_response

    def _ensure_user_login_allowed(self, user: User) -> None:
        """Block token issuance for inactive or deleted users (defense-in-depth)."""
        if getattr(user, "deleted_at", None) is not None:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.USER_ACCOUNT_DELETED,
            )
        if not getattr(user, "is_active", True):
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.USER_INACTIVE,
            )

    def _sync_verified_flags_from_token_payload(self, *, user: User, payload: dict) -> None:
        updated = False
        if payload.get("email_verified") is True and not user.is_email_verified:
            user.is_email_verified = True
            updated = True
        if payload.get("phone_number_verified") is True and not user.is_phone_verified:
            user.is_phone_verified = True
            updated = True
        if updated:
            self._repo.commit()

    def _requires_password_set(self, user: User) -> bool:
        return bool(user.profile is not None and user.profile.password_set_at is None)

    def _client_meta(self, request: Request | None) -> tuple[str | None, str | None]:
        if request is None:
            return None, None
        user_agent = (request.headers.get("user-agent") or "").strip() or None
        xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        client_host = request.client.host if request.client else None
        ip = xff or client_host or None
        return user_agent, ip

    def _remember_me_session_seconds(self, settings: Settings) -> int:
        days = int(getattr(settings, "remember_me_session_days", 0))
        if days > 0:
            from_days = days * 24 * 60 * 60
            return min(from_days, RememberMeConstants.MAX_SESSION_SECONDS)
        return RememberMeConstants.MAX_SESSION_SECONDS

    def _remember_me_expires_at(self, settings: Settings) -> datetime:
        return datetime.now(timezone.utc) + timedelta(
            seconds=self._remember_me_session_seconds(settings)
        )

    def _remaining_remember_me_seconds(self, *, expires_at: datetime, now: datetime) -> int:
        remaining = int((expires_at - now).total_seconds())
        return max(0, min(remaining, RememberMeConstants.MAX_SESSION_SECONDS))

    def _apply_enriched_access_token(self, *, auth_result: dict, user: User) -> dict:
        """Replace Cognito access JWT with API-issued JWT (same response key, enriched payload)."""
        result = dict(auth_result)
        expires_in = int(result.get("ExpiresIn") or result.get("expires_in") or 3600)
        user_with_roles = self._repo.get_user_by_id_with_roles(user.id) or user
        enriched = create_auth_access_token(user=user_with_roles, expires_in=expires_in)
        if "AccessToken" in result:
            result["AccessToken"] = enriched
        if "access_token" in result:
            result["access_token"] = enriched
        return result

    def _token_response_from_cognito_auth(
        self,
        *,
        auth_result: dict,
        requires_password_set: bool,
        omit_refresh_in_body: bool,
        remember_me_cookie: bool,
    ) -> TokenResponse:
        rt = auth_result.get("RefreshToken") or auth_result.get("refresh_token")
        access = auth_result.get("AccessToken") or auth_result.get("access_token")
        expires_in = int(auth_result.get("ExpiresIn") or auth_result.get("expires_in") or 3600)
        return TokenResponse(
            access_token=access,
            refresh_token=None if omit_refresh_in_body else rt,
            id_token=auth_result.get("IdToken") or auth_result.get("id_token"),
            expires_in=expires_in,
            requires_password_set=requires_password_set,
            remember_me_cookie=remember_me_cookie,
        )

    def _persist_remember_me(
        self,
        *,
        user: User,
        cognito_refresh_token: str,
        cognito_username: str,
        request: Request | None,
    ) -> tuple[str, int]:
        settings = get_settings()
        session_seconds = self._remember_me_session_seconds(settings)
        user_agent, ip_address = self._client_meta(request)
        opaque = generate_opaque_remember_me_token()
        self._remember_me_repo.create(
            user_id=user.id,
            token_hash=hash_remember_me_opaque_token(opaque),
            cognito_refresh_encrypted=encrypt_refresh_token(settings, cognito_refresh_token),
            cognito_username=cognito_username,
            expires_at=self._remember_me_expires_at(settings),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._repo.commit()
        return opaque, session_seconds

    def _resolve_cognito_refresh_username(
        self,
        *,
        user: User,
        auth_result: dict,
        fallback_username: str,
    ) -> str:
        """Return Cognito USERNAME for SECRET_HASH on refresh (same as login: user email)."""
        _ = auth_result  # enrichment may replace access token; identity comes from user record
        email = cognito_refresh_username(user)
        if email:
            return email
        return (fallback_username or "").strip().lower()

    def _resolve_cognito_username_for_refresh(self, username: str) -> str:
        """Map refresh ``username`` (email, Cognito sub, or legacy DB UUID) to Cognito refresh username."""
        value = (username or "").strip()
        if not value:
            return value
        if "@" in value:
            user = self._repo.get_user_by_email_or_phone_with_profile(value.lower())
            if user:
                return cognito_refresh_username(user)
            return value.lower()
        try:
            user_id = uuid.UUID(value)
            user = self._repo.get_user_by_id_with_profile(user_id)
            if user:
                return cognito_refresh_username(user)
        except (ValueError, TypeError):
            pass
        user = self._repo.get_user_by_cognito_sub_with_profile(value)
        if user:
            return cognito_refresh_username(user)
        return value

    def _resolve_user_for_refresh_access_token(self, *, access_token: str) -> tuple[User, dict]:
        api_payload = decode_auth_access_token(access_token)
        if api_payload:
            user = None
            user_id = parse_user_id_from_payload(api_payload)
            if user_id is not None:
                user = self._repo.get_user_by_id_with_profile(user_id)
            if user is None:
                cognito_sub = cognito_sub_from_payload(api_payload) or (api_payload.get("sub") or "").strip()
                if cognito_sub:
                    user = self._repo.get_user_by_cognito_sub_with_profile(cognito_sub)
            if user is None and api_payload.get("email"):
                user = self._repo.get_user_by_email_or_phone_with_profile(str(api_payload["email"]))
            if not user:
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail=ErrorMessages.INVALID_TOKEN,
                )
            return user, api_payload

        payload = cognito_service.verify_token(access_token)
        if not payload:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_TOKEN,
            )

        cognito_sub = payload.get("sub")
        if not cognito_sub:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_TOKEN,
            )

        user = self._repo.get_user_by_cognito_sub_with_profile(cognito_sub)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_TOKEN,
            )
        return user, payload

    def _extract_social_identity(self, *, auth_result: dict) -> tuple[dict, str, str, str]:
        id_token = auth_result.get("id_token")
        if not id_token:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.SOCIAL_AUTH_FAILED,
            )

        payload = cognito_service.verify_token(id_token)
        if not payload:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.SOCIAL_AUTH_FAILED,
            )

        email = payload.get("email")
        cognito_sub = payload.get("sub")
        if not email or not cognito_sub:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.SOCIAL_AUTH_FAILED,
            )
        full_name = payload.get("name", Defaults.SOCIAL_USER_DEFAULT_NAME)
        return payload, email, cognito_sub, full_name

    def _normalize_requested_login_role(self, role: str) -> str:
        """Normalize optional login role hint to internal DB role names."""
        value = (role or "").strip().lower()
        # Frontend-friendly alias for agency admin login.
        if value == "agency_admin":
            return UserRoles.ADMIN
        return value

    def _validate_optional_login_role(self, *, user: User, requested_role: str | None) -> None:
        """Validate optional role hint before Cognito auth; no-op when role is omitted."""
        if requested_role is None or not requested_role.strip():
            return
        normalized = self._normalize_requested_login_role(requested_role)
        user_with_roles = self._repo.get_user_by_id_with_roles(user.id) or user
        assigned_roles = {
            (getattr(role, "name", "") or "").strip().lower()
            for role in (getattr(user_with_roles, "roles", None) or [])
            if getattr(role, "name", None)
        }
        if normalized not in assigned_roles:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.ROLE_MISMATCHED,
            )

    # Signup flows --------------------------------------------------------

    def signup(self, user_in: UserCreate) -> StandardResponse[UserResponse]:
        if self._repo.user_exists_by_email_or_phone(
            email=user_in.email, phone=user_in.phone_number
        ):
            api_logger.warning(
                format_log_message(
                    LogMessages.Auth.SIGNUP_ATTEMPT_EXISTING,
                    email=user_in.email,
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_EXISTS,
            )

        requested_role = (user_in.role or "").strip()
        registration_role = None
        if requested_role:
            normalized_role = self._normalize_requested_login_role(requested_role)
            registration_role = self._repo.get_role_by_name(normalized_role)
            if registration_role is None:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.ROLE_NOT_FOUND,
                )

        try:
            cognito_response = cognito_service.signup(
                email=user_in.email,
                password=user_in.password,
                full_name=user_in.full_name,
                phone_number=user_in.phone_number,
            )
            cognito_sub = cognito_response.get(CognitoConstants.USER_SUB)

            db_user = self._repo.create_user(
                email=user_in.email,
                full_name=user_in.full_name,
                phone_number=user_in.phone_number,
                cognito_sub=cognito_sub,
                is_active=True,
            )

            role = registration_role or self._repo.get_role_by_name(UserRoles.REGISTERED_USER)
            if role:
                db_user.roles.append(role)

            self._repo.commit()
            self._repo.refresh(db_user)

            user_response = UserResponse.model_validate(db_user)
            self._sign_user_response(user_response)
            return create_success_response(
                data=user_response, message=SuccessMessages.USER_REGISTERED
            )
        except Exception as e:  # pragma: no cover - defensive
            self._repo.rollback()
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def signup_admin(self, user_in: UserCreate) -> StandardResponse[UserResponse]:
        if self._repo.user_exists_by_email_or_phone(
            email=user_in.email, phone=user_in.phone_number
        ):
            api_logger.warning(
                format_log_message(
                    LogMessages.Auth.SIGNUP_ATTEMPT_EXISTING,
                    email=user_in.email,
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_EXISTS,
            )

        try:
            cognito_response = cognito_service.signup(
                email=user_in.email,
                password=user_in.password,
                full_name=user_in.full_name,
                phone_number=user_in.phone_number,
            )
            cognito_sub = cognito_response.get(CognitoConstants.USER_SUB)

            db_user = self._repo.create_user(
                email=user_in.email,
                full_name=user_in.full_name,
                phone_number=user_in.phone_number,
                cognito_sub=cognito_sub,
                is_active=True,
            )
            role = self._repo.get_role_by_name(UserRoles.ADMIN)
            if role:
                db_user.roles.append(role)

            self._repo.commit()
            self._repo.refresh(db_user)

            user_response = UserResponse.model_validate(db_user)
            self._sign_user_response(user_response)
            return create_success_response(
                data=user_response, message=SuccessMessages.ADMIN_REGISTERED
            )
        except Exception as e:  # pragma: no cover - defensive
            self._repo.rollback()
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def confirm_signup(self, confirm_in: ConfirmSignupRequest) -> StandardResponse[bool]:
        try:
            cognito_service.confirm_signup(confirm_in.email, confirm_in.code)
            user = self._repo.get_user_by_email(confirm_in.email)
            if user:
                user.is_email_verified = True
                self._repo.commit()
            return create_success_response(
                data=True, message=SuccessMessages.ACCOUNT_CONFIRMED
            )
        except ClientError as e:
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def resend_confirmation(self, req: ResendConfirmationRequest) -> StandardResponse[bool]:
        try:
            cognito_service.resend_confirmation_code(req.email)
            return create_success_response(
                data=True, message=SuccessMessages.CONFIRMATION_CODE_SENT
            )
        except ClientError as e:
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def _audit_failed_password_login(self, *, user_id: str, email: str, request: Request | None) -> None:
        _, ip = self._client_meta(request)
        api_logger.warning(
            format_log_message(
                LogMessages.Auth.PASSWORD_LOGIN_FAILED_AUDIT,
                user_id=user_id,
                email=email,
                ip=ip or "-",
                reason="invalid_password",
            )
        )

    # Login flows ---------------------------------------------------------

    def login_password(
        self, login_in: LoginRequest, request: Request | None = None
    ) -> tuple[StandardResponse[TokenResponse], RememberMeHttpEffect]:
        now = datetime.now(timezone.utc)
        user = self._repo.get_user_by_email_or_phone_with_profile(login_in.username)
        if not user:
            self._audit_failed_password_login(
                user_id="-", email=login_in.username, request=request
            )
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_LOGIN_CREDENTIALS_UNIFIED,
            )

        self._validate_optional_login_role(user=user, requested_role=login_in.role)
        self._ensure_user_login_allowed(user)
        user = self._repo.acquire_user_for_password_login_security(user.id)
        if user.password_login_locked_until is not None and user.password_login_locked_until > now:
            self._repo.commit()
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.account_locked_failed_password_logins(
                    lock_duration_minutes=get_settings().password_login_lock_duration_minutes
                ),
            )
        self._repo.commit()

        cognito_username = user.email
        try:
            auth_result = cognito_service.login_password(
                cognito_username, login_in.password
            )
            # Sync verified flags during explicit auth flow (not in request dependencies).
            access_token = auth_result.get("AccessToken")
            if access_token:
                payload = cognito_service.verify_token(access_token)
                if payload:
                    self._sync_verified_flags_from_token_payload(user=user, payload=payload)
            requires_password_set = self._requires_password_set(user)
            cognito_refresh = auth_result.get("RefreshToken")
            remember_me = bool(login_in.remember_me)
            if remember_me:
                if not cognito_refresh:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=ErrorMessages.REMEMBER_ME_NO_REFRESH_TOKEN,
                    )
                opaque, max_age = self._persist_remember_me(
                    user=user,
                    cognito_refresh_token=cognito_refresh,
                    cognito_username=self._resolve_cognito_refresh_username(
                        user=user,
                        auth_result=auth_result,
                        fallback_username=cognito_username,
                    ),
                    request=request,
                )
                self._repo.reset_password_login_security_by_id(user.id)
                self._repo.commit()
                enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user)
                return create_success_response(
                    data=self._token_response_from_cognito_auth(
                        auth_result=enriched,
                        requires_password_set=requires_password_set,
                        omit_refresh_in_body=True,
                        remember_me_cookie=True,
                    ),
                    message=SuccessMessages.LOGIN_SUCCESSFUL,
                ), RememberMeHttpEffect(
                    set_cookie_opaque=opaque,
                    cookie_max_age_seconds=max_age,
                )

            self._repo.reset_password_login_security_by_id(user.id)
            self._repo.commit()
            enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user)
            return create_success_response(
                data=self._token_response_from_cognito_auth(
                    auth_result=enriched,
                    requires_password_set=requires_password_set,
                    omit_refresh_in_body=False,
                    remember_me_cookie=False,
                ),
                message=SuccessMessages.LOGIN_SUCCESSFUL,
            ), RememberMeHttpEffect()
        except HTTPException:
            self._repo.rollback()
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "UserNotConfirmedException":
                self._repo.commit()
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail=ErrorMessages.USER_NOT_CONFIRMED,
                )
            if error_code == "TooManyRequestsException":
                self._repo.commit()
                raise HTTPException(
                    status_code=HTTPStatus.TOO_MANY_REQUESTS,
                    detail=ErrorMessages.COGNITO_RATE_LIMITED,
                )
            self._repo.record_failed_password_login_attempt(user.id)
            self._repo.commit()
            self._audit_failed_password_login(
                user_id=str(user.id), email=user.email, request=request
            )
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_LOGIN_CREDENTIALS_UNIFIED,
            )
        except Exception:  # pragma: no cover - defensive
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_LOGIN_CREDENTIALS_UNIFIED,
            )

    def login_otp_request(self, otp_req: OTPRequest) -> StandardResponse[dict]:
        user = self._repo.get_user_by_email_or_phone_with_profile(otp_req.username)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        self._ensure_user_login_allowed(user)
        cognito_username = user.email
        try:
            response = cognito_service.login_otp_request(cognito_username)
            data = {"session": response.get("Session")}
            challenge_parameters = response.get("ChallengeParameters") or {}
            otp = challenge_parameters.get("otp")
            if otp:
                data["otp"] = otp
            return create_success_response(
                data=data,
                message=SuccessMessages.OTP_SENT,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = (e.response.get("Error") or {}).get("Message", str(e))
            if error_code == "UserNotFoundException":
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=ErrorMessages.USER_NOT_FOUND,
                )
            if error_code == "InvalidParameterException" and CognitoConstants.OTP_ERROR_SUBSTRING in error_msg:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.OTP_NOT_CONFIGURED,
                )
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )
        except Exception as e:  # pragma: no cover - defensive
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def login_otp_verify(
        self, otp_ver: OTPVerify, request: Request | None = None
    ) -> tuple[StandardResponse[TokenResponse], RememberMeHttpEffect]:
        user = self._repo.get_user_by_email_or_phone_with_profile(otp_ver.username)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        self._ensure_user_login_allowed(user)
        cognito_username = user.email
        try:
            auth_result = cognito_service.login_otp_verify(
                otp_ver.session, cognito_username, otp_ver.code
            )
            # Sync verified flags during explicit auth flow (not in request dependencies).
            access_token = auth_result.get("AccessToken")
            if access_token:
                payload = cognito_service.verify_token(access_token)
                if payload:
                    self._sync_verified_flags_from_token_payload(user=user, payload=payload)
            requires_password_set = self._requires_password_set(user)
            cognito_refresh = auth_result.get("RefreshToken")
            remember_me = bool(otp_ver.remember_me)
            if remember_me:
                if not cognito_refresh:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=ErrorMessages.REMEMBER_ME_NO_REFRESH_TOKEN,
                    )
                opaque, max_age = self._persist_remember_me(
                    user=user,
                    cognito_refresh_token=cognito_refresh,
                    cognito_username=self._resolve_cognito_refresh_username(
                        user=user,
                        auth_result=auth_result,
                        fallback_username=cognito_username,
                    ),
                    request=request,
                )
                enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user)
                return create_success_response(
                    data=self._token_response_from_cognito_auth(
                        auth_result=enriched,
                        requires_password_set=requires_password_set,
                        omit_refresh_in_body=True,
                        remember_me_cookie=True,
                    ),
                    message=SuccessMessages.LOGIN_SUCCESSFUL,
                ), RememberMeHttpEffect(
                    set_cookie_opaque=opaque,
                    cookie_max_age_seconds=max_age,
                )

            enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user)
            return create_success_response(
                data=self._token_response_from_cognito_auth(
                    auth_result=enriched,
                    requires_password_set=requires_password_set,
                    omit_refresh_in_body=False,
                    remember_me_cookie=False,
                ),
                message=SuccessMessages.LOGIN_SUCCESSFUL,
            ), RememberMeHttpEffect()
        except HTTPException:
            raise
        except Exception:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_OTP,
            )

    def _refresh_via_body(
        self, body: RefreshRequest, *, settings: Settings
    ) -> StandardResponse[TokenResponse]:
        if settings.cognito_client_secret and not (body.username or "").strip():
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REFRESH_USERNAME_REQUIRED,
            )
        try:
            cognito_username = self._resolve_cognito_username_for_refresh(
                (body.username or "").strip()
            )
            auth_result = cognito_service.refresh_token(
                body.refresh_token or "",
                cognito_username,
            )
            access_token = auth_result["AccessToken"]
            user, payload = self._resolve_user_for_refresh_access_token(access_token=access_token)
            self._ensure_user_login_allowed(user)

            # Keep user attributes in sync during explicit auth flows (not in dependencies).
            self._sync_verified_flags_from_token_payload(user=user, payload=payload)

            requires_password_set = bool(
                user.profile is not None and user.profile.password_set_at is None
            )

            enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user)
            return create_success_response(
                data=self._token_response_from_cognito_auth(
                    auth_result=enriched,
                    requires_password_set=requires_password_set,
                    omit_refresh_in_body=False,
                    remember_me_cookie=False,
                ),
            )
        except HTTPException:
            raise
        except Exception:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_TOKEN,
            )

    def _refresh_via_remember_me_cookie(
        self, *, request: Request, settings: Settings
    ) -> tuple[StandardResponse[TokenResponse], RememberMeHttpEffect]:
        raw = (request.cookies.get(RememberMeConstants.COOKIE_NAME) or "").strip()
        if not raw:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REMEMBER_ME_REFRESH_OR_COOKIE_REQUIRED,
            )
        now = datetime.now(timezone.utc)
        row = self._remember_me_repo.get_active_by_token_hash(hash_remember_me_opaque_token(raw))
        if not row:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.REMEMBER_ME_SESSION_INVALID,
            )
        cognito_rt = decrypt_refresh_token(settings, row.cognito_refresh_encrypted)
        if not cognito_rt:
            self._remember_me_repo.revoke_by_id(row.id, revoked_at=now)
            self._repo.commit()
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.REMEMBER_ME_SESSION_INVALID,
            )
        user = self._repo.get_user_by_id_with_profile(row.user_id)
        if not user:
            self._remember_me_repo.revoke_by_id(row.id, revoked_at=now)
            self._repo.commit()
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.REMEMBER_ME_SESSION_INVALID,
            )
        self._ensure_user_login_allowed(user)
        try:
            auth_result = cognito_service.refresh_token(
                cognito_rt,
                row.cognito_username,
            )
        except ClientError:
            # Backward-compatible recovery for sessions created with a stale username value:
            # retry using the same login identity used by USER_PASSWORD_AUTH (email).
            retry_username = (getattr(user, "email", None) or "").strip().lower()
            if retry_username and retry_username != row.cognito_username:
                try:
                    auth_result = cognito_service.refresh_token(
                        cognito_rt,
                        retry_username,
                    )
                except ClientError:
                    raise HTTPException(
                        status_code=HTTPStatus.UNAUTHORIZED,
                        detail=ErrorMessages.INVALID_TOKEN,
                    )
            else:
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail=ErrorMessages.INVALID_TOKEN,
                )
        access_token = auth_result["AccessToken"]
        user2, payload = self._resolve_user_for_refresh_access_token(access_token=access_token)
        if user2.id != user.id:
            self._remember_me_repo.revoke_by_id(row.id, revoked_at=now)
            self._repo.commit()
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.REMEMBER_ME_SESSION_INVALID,
            )
        self._sync_verified_flags_from_token_payload(user=user2, payload=payload)
        requires_password_set = bool(
            user2.profile is not None and user2.profile.password_set_at is None
        )
        new_cognito_rt = auth_result.get("RefreshToken") or cognito_rt
        new_opaque = generate_opaque_remember_me_token()
        new_enc = encrypt_refresh_token(settings, new_cognito_rt)
        self._remember_me_repo.update_after_rotation(
            row.id,
            new_token_hash=hash_remember_me_opaque_token(new_opaque),
            cognito_refresh_encrypted=new_enc,
            cognito_username=self._resolve_cognito_refresh_username(
                user=user2,
                auth_result=auth_result,
                fallback_username=row.cognito_username,
            ),
            expires_at=row.expires_at,
            last_used_at=now,
        )
        self._repo.commit()
        max_age = self._remaining_remember_me_seconds(expires_at=row.expires_at, now=now)
        enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user2)
        return create_success_response(
            data=self._token_response_from_cognito_auth(
                auth_result=enriched,
                requires_password_set=requires_password_set,
                omit_refresh_in_body=True,
                remember_me_cookie=True,
            ),
        ), RememberMeHttpEffect(
            set_cookie_opaque=new_opaque,
            cookie_max_age_seconds=max_age,
        )

    def refresh_token(
        self,
        body: RefreshRequest,
        *,
        request: Request | None = None,
    ) -> tuple[StandardResponse[TokenResponse], RememberMeHttpEffect]:
        settings = get_settings()
        body_rt = (body.refresh_token or "").strip()
        if body_rt:
            return self._refresh_via_body(body, settings=settings), RememberMeHttpEffect()
        if request is not None:
            return self._refresh_via_remember_me_cookie(request=request, settings=settings)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.REMEMBER_ME_REFRESH_OR_COOKIE_REQUIRED,
        )

    def logout(
        self,
        user: User,
        auth: HTTPAuthorizationCredentials,
    ) -> tuple[StandardResponse[bool], RememberMeHttpEffect]:
        now = datetime.now(timezone.utc)
        self._remember_me_repo.revoke_all_for_user(user.id, revoked_at=now)
        self._repo.commit()
        try:
            # API-issued access tokens are not valid for Cognito global_sign_out.
            if not decode_auth_access_token(auth.credentials):
                cognito_service.logout(auth.credentials)
            api_logger.info(
                format_log_message(LogMessages.Auth.LOGOUT_SUCCESS, email=user.email)
            )
            return create_success_response(
                data=True, message=SuccessMessages.LOGOUT_SUCCESSFUL
            ), RememberMeHttpEffect(clear_cookie=True)
        except Exception as e:  # pragma: no cover - defensive
            api_logger.error(
                format_log_message(LogMessages.Auth.LOGOUT_FAILED, error=str(e))
            )
            return create_success_response(
                data=False, message=ErrorMessages.LOGOUT_FAILED
            ), RememberMeHttpEffect(clear_cookie=True)

    # Password reset / set flows -----------------------------------------

    def forgot_password_request(
        self, fp_req: ForgotPasswordRequest
    ) -> StandardResponse[bool]:
        try:
            cognito_service.forgot_password_request(fp_req.email)
            return create_success_response(
                data=True, message=SuccessMessages.OTP_SENT
            )
        except Exception as e:  # pragma: no cover - defensive
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def forgot_password_confirm(
        self, fp_conf: ForgotPasswordConfirm
    ) -> StandardResponse[bool]:
        try:
            cognito_service.forgot_password_confirm(
                fp_conf.email, fp_conf.code, fp_conf.new_password
            )
            return create_success_response(
                data=True, message=SuccessMessages.PASSWORD_RESET_SUCCESS
            )
        except Exception as e:  # pragma: no cover - defensive
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    def set_password(
        self,
        password_req: SetPasswordRequest,
        current_user: User,
        auth: HTTPAuthorizationCredentials,
    ) -> StandardResponse[bool]:
        try:
            access_token = auth.credentials
            previous_password = password_req.previous_password or ""

            cognito_service.change_password(
                access_token=access_token,
                previous_password=previous_password,
                proposed_password=password_req.password,
            )

            if hasattr(current_user, "profile") and current_user.profile:
                from datetime import datetime

                try:
                    self._repo.refresh(current_user.profile)
                    current_user.profile.password_set_at = datetime.now()
                    self._repo.commit()
                except Exception as db_error:  # pragma: no cover - defensive
                    self._repo.rollback()
                    api_logger.warning(
                        format_log_message(
                            LogMessages.Auth.PASSWORD_SET_AT_UPDATE_FAILED,
                            error=str(db_error),
                        )
                    )

            api_logger.info(
                format_log_message(
                    LogMessages.Auth.PASSWORD_RESET_SUCCESS, email=current_user.email
                )
            )
            return create_success_response(
                data=True, message=SuccessMessages.PASSWORD_RESET_SUCCESS
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NotAuthorizedException":
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_PREVIOUS_PASSWORD_OR_PERMISSIONS,
                )
            if error_code == "InvalidPasswordException":
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.PASSWORD_DOES_NOT_MEET_REQUIREMENTS,
                )
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )
        except Exception as e:  # pragma: no cover - defensive
            server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=server_error,
            )

    # Social login / profile endpoints -----------------------------------

    def social_login(self, provider: str = "Google") -> StandardResponse[dict]:
        login_url = cognito_service.get_social_login_url(provider)
        return create_success_response(data={"url": login_url})

    def get_current_user_profile(self, current_user: User) -> StandardResponse[UserResponse]:
        self._repo.ensure_agent_profile_loaded(current_user)
        # Ensure lazy relationship is resolved while session is active for /auth/me payload.
        _ = getattr(current_user, "agency", None)

        requires_password_set = False
        if current_user.profile:
            self._repo.refresh(current_user.profile)
            requires_password_set = current_user.profile.password_set_at is None

        user_response = UserResponse.model_validate(current_user)
        user_response.requires_password_set = requires_password_set
        self._sign_user_response(user_response)

        return create_success_response(data=user_response, message=None)

    def get_current_user_permissions(
        self,
        current_user: User,
    ) -> StandardResponse[PermissionsResponse]:
        perms = sorted(get_user_permissions(current_user, self._repo._db))
        return create_success_response(
            data=PermissionsResponse(permissions=perms), message=None
        )

    def social_callback(self, code: str) -> StandardResponse[TokenResponse]:
        try:
            auth_result = cognito_service.exchange_code_for_tokens(code)
            payload, email, cognito_sub, full_name = self._extract_social_identity(
                auth_result=auth_result
            )

            user = self._repo.get_user_by_cognito_or_email_including_deleted(
                cognito_sub=cognito_sub,
                email=email,
            )

            if not user:
                user = self._repo.create_user(
                    email=email,
                    full_name=full_name,
                    phone_number=f"social_{cognito_sub[:10]}",
                    cognito_sub=cognito_sub,
                    is_active=True,
                )
                role = self._repo.get_role_by_name(UserRoles.REGISTERED_USER)
                if role:
                    user.roles.append(role)
                self._repo.commit()
                self._repo.refresh(user)
                api_logger.info(
                    format_log_message(
                        LogMessages.Auth.SOCIAL_LOGIN_SUCCESS, email=email
                    )
                )
            else:
                self._ensure_user_login_allowed(user)
                if not user.cognito_sub:
                    user.cognito_sub = cognito_sub
                    self._repo.commit()
                    self._repo.refresh(user)
            # Sync verified flags during explicit social auth flow.
            self._sync_verified_flags_from_token_payload(user=user, payload=payload)

            enriched = self._apply_enriched_access_token(auth_result=auth_result, user=user)
            return create_success_response(
                data=self._token_response_from_cognito_auth(
                    auth_result=enriched,
                    requires_password_set=False,
                    omit_refresh_in_body=False,
                    remember_me_cookie=False,
                ),
                message=SuccessMessages.SOCIAL_LOGIN_SUCCESSFUL,
            )
        except HTTPException:
            # Preserve explicit auth errors (inactive/deleted, etc.)
            raise
        except Exception as e:  # pragma: no cover - defensive
            api_logger.error(
                format_log_message(
                    LogMessages.Auth.SOCIAL_AUTH_FAILED_LOG,
                    email=LogMessages.Auth.UNKNOWN_EMAIL,
                    error=str(e),
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.SOCIAL_AUTH_FAILED,
            )

