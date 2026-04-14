"""Authentication and user profile endpoints.

This router exposes signup/login flows (password, OTP, social), session management,
and authenticated profile/permissions endpoints. Most business logic is delegated
to `AuthService`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1.deps.auth import get_auth_service
from app.api.v1.deps.security import get_current_user, require_role, security
from app.core.limiter import limiter
from app.models.user import User
from app.utils.constants import Defaults, RateLimits, UserRoles
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
from app.services.auth_service import AuthService
from app.utils.responses import StandardResponse
from app.utils.constants import ErrorMessages
from app.utils.status_codes import HTTPStatus
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger

router = APIRouter()


@router.post("/signup")
@limiter.limit(RateLimits.SIGNUP)
def signup(
    request: Request,
    user_in: UserCreate,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[UserResponse]:
    """Register a new user. Requires email confirmation via /confirm-signup."""
    return service.signup(user_in)


@router.post("/signup/admin")
def signup_admin(
    user_in: UserCreate,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[UserResponse]:
    """Deprecated: Admin signup is not available via public API."""
    api_logger.warning(format_log_message(LogMessages.ApiRoutes.AUTH_DEPRECATED_ADMIN_SIGNUP))
    raise HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        detail=ErrorMessages.NOT_FOUND,
    )


@router.post("/confirm-signup")
def confirm_signup(
    confirm_in: ConfirmSignupRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Confirm sign-up with the code sent by Cognito. Marks email as verified in the app DB."""
    return service.confirm_signup(confirm_in)


@router.post("/resend-confirmation")
def resend_confirmation(
    req: ResendConfirmationRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Resend the email confirmation code to the user."""
    return service.resend_confirmation(req)


@router.post("/login/password")
@limiter.limit(RateLimits.LOGIN_PASSWORD)
def login_password(
    request: Request,
    login_in: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Authenticate with email or phone number + password. Returns access and refresh tokens."""
    return service.login_password(login_in)


@router.post("/login/otp/request")
@limiter.limit(RateLimits.LOGIN_OTP_REQUEST)
def login_otp_request(
    request: Request,
    otp_req: OTPRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[dict]:
    """Request OTP for passwordless login (email or phone). Requires Cognito custom auth (Lambda)."""
    return service.login_otp_request(otp_req)


@router.post("/login/otp/verify")
@limiter.limit(RateLimits.LOGIN_OTP_VERIFY)
def login_otp_verify(
    request: Request,
    otp_ver: OTPVerify,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Verify OTP and return tokens. Requires session from /login/otp/request."""
    return service.login_otp_verify(otp_ver)


@router.post("/refresh")
def refresh_token(
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Refresh access token using refresh_token in request body."""
    return service.refresh_token(body)


@router.post("/logout")
def logout(
    user: Annotated[User, Depends(get_current_user)],
    auth: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Invalidate the current user's Cognito session."""
    return service.logout(user, auth)


@router.post("/forgot-password/request")
@limiter.limit(RateLimits.FORGOT_PASSWORD_REQUEST)
def forgot_password_request(
    request: Request,
    fp_req: ForgotPasswordRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Send password reset code to the user's email."""
    return service.forgot_password_request(fp_req)


@router.post("/forgot-password/confirm")
@limiter.limit(RateLimits.FORGOT_PASSWORD_CONFIRM)
def forgot_password_confirm(
    request: Request,
    fp_conf: ForgotPasswordConfirm,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Confirm password reset with code and new password."""
    return service.forgot_password_confirm(fp_conf)


@router.post("/set-password")
def set_password(
    password_req: SetPasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    auth: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Set or change password for the authenticated user."""
    return service.set_password(password_req, current_user, auth)


@router.post("/change-password")
def change_password(
    password_req: SetPasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    auth: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Change password for the authenticated user using the current password."""
    return service.set_password(password_req, current_user, auth)


@router.get("/social-login")
def social_login(
    service: Annotated[AuthService, Depends(get_auth_service)],
    provider: str = Defaults.DEFAULT_SOCIAL_PROVIDER,
) -> StandardResponse[dict]:
    """Get the social login URL for a specific provider."""
    return service.social_login(provider)


@router.get("/me")
def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[UserResponse]:
    """Return the currently authenticated user's profile."""
    return service.get_current_user_profile(current_user)


@router.get("/me/permissions")
def get_current_user_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[PermissionsResponse]:
    """Return the current user's permission codes (from roles and inherited assignments)."""
    return service.get_current_user_permissions(current_user)


@router.get("/callback")
def social_callback(
    code: str,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Handle the OAuth2 callback and return tokens."""
    return service.social_callback(code)
