from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
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
from app.utils.constants import (
    Defaults,
    ErrorMessages,
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

    def __init__(self, repository: AuthRepository) -> None:
        self._repo = repository

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

        try:
            cognito_response = cognito_service.signup(
                email=user_in.email,
                password=user_in.password,
                full_name=user_in.full_name,
                phone_number=user_in.phone_number,
            )
            cognito_sub = cognito_response.get("UserSub")

            db_user = self._repo.create_user(
                email=user_in.email,
                full_name=user_in.full_name,
                phone_number=user_in.phone_number,
                cognito_sub=cognito_sub,
                is_active=True,
            )

            role = self._repo.get_role_by_name(UserRoles.REGISTERED_USER)
            if role:
                db_user.roles.append(role)

            self._repo.commit()
            self._repo.refresh(db_user)

            return create_success_response(
                data=db_user, message=SuccessMessages.USER_REGISTERED
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
            cognito_sub = cognito_response.get("UserSub")

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

            return create_success_response(
                data=db_user, message=SuccessMessages.ADMIN_REGISTERED
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

    # Login flows ---------------------------------------------------------

    def login_password(self, login_in: LoginRequest) -> StandardResponse[TokenResponse]:
        user = self._repo.get_user_by_email_or_phone_with_profile(login_in.username)
        if not user:
            api_logger.warning(
                format_log_message(
                    LogMessages.Auth.LOGIN_FAILED,
                    email=login_in.username,
                    error=ErrorMessages.USER_NOT_FOUND,
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
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
                    updated = False
                    if payload.get("email_verified") is True and not user.is_email_verified:
                        user.is_email_verified = True
                        updated = True
                    if payload.get("phone_number_verified") is True and not user.is_phone_verified:
                        user.is_phone_verified = True
                        updated = True
                    if updated:
                        self._repo.commit()
            requires_password_set = bool(
                user.profile is not None and user.profile.password_set_at is None
            )
            return create_success_response(
                data=TokenResponse(
                    access_token=auth_result["AccessToken"],
                    refresh_token=auth_result.get("RefreshToken"),
                    id_token=auth_result.get("IdToken"),
                    expires_in=auth_result["ExpiresIn"],
                    requires_password_set=requires_password_set,
                ),
                message=SuccessMessages.LOGIN_SUCCESSFUL,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "UserNotFoundException":
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=ErrorMessages.USER_NOT_FOUND,
                )
            if error_code == "UserNotConfirmedException":
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail=ErrorMessages.USER_NOT_CONFIRMED,
                )
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_CREDENTIALS,
            )
        except Exception:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_CREDENTIALS,
            )

    def login_otp_request(self, otp_req: OTPRequest) -> StandardResponse[dict]:
        user = self._repo.get_user_by_email_or_phone_with_profile(otp_req.username)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        cognito_username = user.email
        try:
            response = cognito_service.login_otp_request(cognito_username)
            return create_success_response(
                data={"session": response.get("Session")},
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
            if error_code == "InvalidParameterException" and "Custom auth lambda trigger" in error_msg:
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

    def login_otp_verify(self, otp_ver: OTPVerify) -> StandardResponse[TokenResponse]:
        user = self._repo.get_user_by_email_or_phone_with_profile(otp_ver.username)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
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
                    updated = False
                    if payload.get("email_verified") is True and not user.is_email_verified:
                        user.is_email_verified = True
                        updated = True
                    if payload.get("phone_number_verified") is True and not user.is_phone_verified:
                        user.is_phone_verified = True
                        updated = True
                    if updated:
                        self._repo.commit()
            requires_password_set = bool(
                user.profile is not None and user.profile.password_set_at is None
            )
            return create_success_response(
                data=TokenResponse(
                    access_token=auth_result["AccessToken"],
                    refresh_token=auth_result.get("RefreshToken"),
                    id_token=auth_result.get("IdToken"),
                    expires_in=auth_result["ExpiresIn"],
                    requires_password_set=requires_password_set,
                ),
                message=SuccessMessages.LOGIN_SUCCESSFUL,
            )
        except Exception:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_OTP,
            )

    def refresh_token(self, body: RefreshRequest) -> StandardResponse[TokenResponse]:
        settings = get_settings()
        if settings.cognito_client_secret and not (body.username or "").strip():
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REFRESH_USERNAME_REQUIRED,
            )
        try:
            auth_result = cognito_service.refresh_token(
                body.refresh_token,
                (body.username or "").strip(),
            )
            access_token = auth_result["AccessToken"]

            requires_password_set = False
            payload = cognito_service.verify_token(access_token)
            if payload:
                cognito_sub = payload.get("sub")
                if cognito_sub:
                    user = self._repo.get_user_by_cognito_sub_with_profile(cognito_sub)
                    if user:
                        # Keep user attributes in sync during explicit auth flows (not in dependencies).
                        updated = False
                        if payload.get("email_verified") is True and not user.is_email_verified:
                            user.is_email_verified = True
                            updated = True
                        if payload.get("phone_number_verified") is True and not user.is_phone_verified:
                            user.is_phone_verified = True
                            updated = True
                        if updated:
                            self._repo.commit()

                    if (
                        user
                        and user.profile
                        and user.profile.password_set_at is None
                    ):
                        requires_password_set = True

            return create_success_response(
                data=TokenResponse(
                    access_token=access_token,
                    refresh_token=auth_result.get("RefreshToken"),
                    id_token=auth_result.get("IdToken"),
                    expires_in=auth_result["ExpiresIn"],
                    requires_password_set=requires_password_set,
                )
            )
        except Exception:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail=ErrorMessages.INVALID_TOKEN,
            )

    def logout(self, user: User, auth: HTTPAuthorizationCredentials) -> StandardResponse[bool]:
        try:
            cognito_service.logout(auth.credentials)
            api_logger.info(
                format_log_message(LogMessages.Auth.LOGOUT_SUCCESS, email=user.email)
            )
            return create_success_response(
                data=True, message=SuccessMessages.LOGOUT_SUCCESSFUL
            )
        except Exception as e:  # pragma: no cover - defensive
            api_logger.error(
                format_log_message(LogMessages.Auth.LOGOUT_FAILED, error=str(e))
            )
            return create_success_response(
                data=False, message=ErrorMessages.LOGOUT_FAILED
            )

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
                        f"Failed to update password_set_at: {str(db_error)}"
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
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail="Invalid previous password or insufficient permissions",
                )
            if error_code == "InvalidPasswordException":
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="Password does not meet requirements",
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

        requires_password_set = False
        if current_user.profile:
            self._repo.refresh(current_user.profile)
            requires_password_set = current_user.profile.password_set_at is None

        user_response = UserResponse.model_validate(current_user)
        user_response.requires_password_set = requires_password_set

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
            id_token = auth_result.get("id_token")

            payload = cognito_service.verify_token(id_token)
            if not payload:
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail=ErrorMessages.SOCIAL_AUTH_FAILED,
                )

            email = payload.get("email")
            cognito_sub = payload.get("sub")
            full_name = payload.get("name", Defaults.SOCIAL_USER_DEFAULT_NAME)

            user = self._repo.get_user_by_cognito_or_email(
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
            elif not user.cognito_sub:
                user.cognito_sub = cognito_sub
                self._repo.commit()
                self._repo.refresh(user)
            # Sync verified flags during explicit social auth flow.
            updated = False
            if payload.get("email_verified") is True and not user.is_email_verified:
                user.is_email_verified = True
                updated = True
            if payload.get("phone_number_verified") is True and not user.is_phone_verified:
                user.is_phone_verified = True
                updated = True
            if updated:
                self._repo.commit()

            return create_success_response(
                data=TokenResponse(
                    access_token=auth_result["access_token"],
                    refresh_token=auth_result.get("refresh_token"),
                    id_token=auth_result.get("id_token"),
                    expires_in=auth_result["expires_in"],
                ),
                message=SuccessMessages.SOCIAL_LOGIN_SUCCESSFUL,
            )
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

