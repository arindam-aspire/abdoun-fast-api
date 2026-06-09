"""Authentication and user profile endpoints.

This router exposes signup/login flows (password, OTP, social), session management,
and authenticated profile/permissions endpoints. Most business logic is delegated
to `AuthService`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1.deps.auth import get_auth_service, get_profile_update_service
from app.api.v1.deps.media_urls import get_media_url_signer
from app.api.v1.deps.profile_picture_upload import get_profile_picture_upload_service
from app.api.v1.deps.security import get_current_user, require_role, security
from app.core.config import get_settings
from app.core.limiter import limiter
from app.models.user import User
from app.utils.constants import ApiDocs, Defaults, RateLimits, SuccessMessages, UserRoles
from app.schemas.user import (
    ConfirmSignupRequest,
    ForgotPasswordConfirm,
    ForgotPasswordRequest,
    LoginRequest,
    OTPRequest,
    OTPVerify,
    PermissionsResponse,
    ProfilePictureUploadData,
    ProfilePictureUploadRequest,
    ProfileUpdateRequest,
    ProfileUpdateRequestResponse,
    ProfileUpdateVerifyRequest,
    ProfileUpdateVerifyResponse,
    RefreshRequest,
    ResendConfirmationRequest,
    SetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.remember_me_http_effect import apply_remember_me_http_effect
from app.services.media_url_signer import MediaUrlSigner
from app.services.profile_picture_upload_service import ProfilePictureUploadService
from app.services.profile_update_service import ProfileUpdateService
from app.utils.responses import StandardResponse, create_success_response
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
    response: Response,
    login_in: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Authenticate with email or phone + password.

    When ``rememberMe`` / ``remember_me`` is true, the Cognito refresh token is stored
    server-side (encrypted) and a high-entropy opaque token is set in an HttpOnly cookie
    (max 30 days). The JSON body omits ``refresh_token`` in that case; use ``remember_me_cookie``
    on ``TokenResponse`` to detect this mode.
    """
    std, effect = service.login_password(login_in, request)
    apply_remember_me_http_effect(response=response, settings=get_settings(), effect=effect)
    return std


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
    response: Response,
    otp_ver: OTPVerify,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Verify OTP and return tokens; supports ``rememberMe`` like password login (HttpOnly cookie)."""
    std, effect = service.login_otp_verify(otp_ver, request)
    apply_remember_me_http_effect(response=response, settings=get_settings(), effect=effect)
    return std


@router.post("/refresh")
def refresh_token(
    request: Request,
    response: Response,
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[TokenResponse]:
    """Refresh access token using refresh_token in the body or the HttpOnly Remember Me cookie."""
    std, effect = service.refresh_token(body, request=request)
    apply_remember_me_http_effect(response=response, settings=get_settings(), effect=effect)
    return std


@router.post("/logout")
def logout(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    auth: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[bool]:
    """Invalidate Cognito session, revoke all Remember Me DB sessions for this user, and clear the HttpOnly cookie."""
    std, effect = service.logout(user, auth)
    apply_remember_me_http_effect(response=response, settings=get_settings(), effect=effect)
    return std


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
    provider: str = Query(
        Defaults.DEFAULT_SOCIAL_PROVIDER,
        description=ApiDocs.SOCIAL_LOGIN_PROVIDER,
    ),
) -> StandardResponse[dict]:
    """Get the Cognito Hosted UI URL for Google or Facebook sign-in."""
    return service.social_login(provider)


@router.get("/me")
def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> StandardResponse[UserResponse]:
    """Return the currently authenticated user's profile."""
    return service.get_current_user_profile(current_user)


@router.post(
    "/me/profile-picture",
    response_model=StandardResponse[ProfilePictureUploadData],
)
def upload_profile_picture(
    body: ProfilePictureUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    upload_service: Annotated[ProfilePictureUploadService, Depends(get_profile_picture_upload_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
) -> StandardResponse[ProfilePictureUploadData]:
    """Return a presigned PUT URL for the profile image and persist the public URL (same strategy as property media presigned flow)."""
    data = upload_service.initiate_upload(user=current_user, body=body)
    media_signer.apply_profile_picture_upload_data(data)
    return create_success_response(data=data, message=SuccessMessages.PROFILE_PICTURE_UPLOADED)


@router.patch(
    "/me/profile/request",
    response_model=StandardResponse[ProfileUpdateRequestResponse],
)
@limiter.limit(RateLimits.PROFILE_UPDATE_REQUEST)
def request_profile_update(
    request: Request,
    body: ProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    profile: Annotated[ProfileUpdateService, Depends(get_profile_update_service)],
):
    """Apply name immediately; create OTP challenges for email/phone when those change."""
    data = profile.request_profile_update(current_user=current_user, body=body)
    return create_success_response(data=data, message=data.message)


@router.post(
    "/me/profile/verify",
    response_model=StandardResponse[ProfileUpdateVerifyResponse],
)
@limiter.limit(RateLimits.PROFILE_OTP_VERIFY)
def verify_profile_update(
    request: Request,
    body: ProfileUpdateVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    profile: Annotated[ProfileUpdateService, Depends(get_profile_update_service)],
):
    """Verify OTP(s) and persist email/phone changes."""
    data = profile.verify_profile_update(current_user=current_user, body=body)
    return create_success_response(data=data, message=data.message)


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
