from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1.deps.auth import get_auth_service
from app.api.v1.deps.security import get_current_user, require_role, security
from app.core.limiter import limiter
from app.models.user import User
from app.utils.constants import UserRoles
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

router = APIRouter()


@router.post("/signup", response_model=StandardResponse[UserResponse])
@limiter.limit("10/minute")
def signup(
    request: Request,
    user_in: UserCreate,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[UserResponse]:
    """Register a new user. Requires email confirmation via /confirm-signup."""
    return service.signup(user_in)


@router.post("/signup/admin", response_model=StandardResponse[UserResponse])
@limiter.limit("5/minute")
def signup_admin(
    request: Request,
    user_in: UserCreate,
    current_user: User = require_role(UserRoles.ADMIN),
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[UserResponse]:
    """Register a new Admin user. Requires authenticated admin. Same payload as normal signup; assigns Admin role."""
    return service.signup_admin(user_in)


@router.post("/confirm-signup", response_model=StandardResponse[bool])
def confirm_signup(
    confirm_in: ConfirmSignupRequest,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[bool]:
    """Confirm sign-up with the code sent by Cognito. Marks email as verified in the app DB."""
    return service.confirm_signup(confirm_in)


@router.post("/resend-confirmation", response_model=StandardResponse[bool])
def resend_confirmation(
    req: ResendConfirmationRequest,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[bool]:
    """Resend the email confirmation code to the user."""
    return service.resend_confirmation(req)


@router.post("/login/password", response_model=StandardResponse[TokenResponse])
@limiter.limit("5/minute")
def login_password(
    request: Request,
    login_in: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[TokenResponse]:
    """Authenticate with email or phone number + password. Returns access and refresh tokens."""
    return service.login_password(login_in)


@router.post("/login/otp/request", response_model=StandardResponse[dict])
@limiter.limit("3/minute")
def login_otp_request(
    request: Request,
    otp_req: OTPRequest,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[dict]:
    """Request OTP for passwordless login (email or phone). Requires Cognito custom auth (Lambda)."""
    return service.login_otp_request(otp_req)


@router.post("/login/otp/verify", response_model=StandardResponse[TokenResponse])
@limiter.limit("5/minute")
def login_otp_verify(
    request: Request,
    otp_ver: OTPVerify,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[TokenResponse]:
    """Verify OTP and return tokens. Requires session from /login/otp/request."""
    return service.login_otp_verify(otp_ver)


@router.post("/refresh", response_model=StandardResponse[TokenResponse])
def refresh_token(
    body: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[TokenResponse]:
    """Refresh access token using refresh_token in request body."""
    return service.refresh_token(body)


@router.post("/logout", response_model=StandardResponse[bool])
def logout(
    user: User = Depends(get_current_user),
    auth: HTTPAuthorizationCredentials = Depends(security),
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[bool]:
    """Invalidate the current user's Cognito session."""
    return service.logout(user, auth)


@router.post("/forgot-password/request", response_model=StandardResponse[bool])
@limiter.limit("3/minute")
def forgot_password_request(
    request: Request,
    fp_req: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[bool]:
    """Send password reset code to the user's email."""
    return service.forgot_password_request(fp_req)


@router.post("/forgot-password/confirm", response_model=StandardResponse[bool])
@limiter.limit("3/minute")
def forgot_password_confirm(
    request: Request,
    fp_conf: ForgotPasswordConfirm,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[bool]:
    """Confirm password reset with code and new password."""
    return service.forgot_password_confirm(fp_conf)


@router.post("/set-password", response_model=StandardResponse[bool])
def set_password(
    password_req: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    auth: HTTPAuthorizationCredentials = Depends(security),
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[bool]:
    """
    Set or change password for the authenticated user.
    """
    return service.set_password(password_req, current_user, auth)


@router.get("/social-login", response_model=StandardResponse[dict])
def social_login(
    provider: str = "Google",
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[dict]:
    """Get the social login URL for a specific provider."""
    return service.social_login(provider)


@router.get("/me", response_model=StandardResponse[UserResponse])
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[UserResponse]:
    """Return the currently authenticated user's profile."""
    return service.get_current_user_profile(current_user)


@router.get("/me/permissions", response_model=StandardResponse[PermissionsResponse])
def get_current_user_permissions(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[PermissionsResponse]:
    """Return the current user's permission codes (from roles and inherited assignments)."""
    return service.get_current_user_permissions(current_user)


@router.get("/callback", response_model=StandardResponse[TokenResponse])
def social_callback(
    code: str,
    service: AuthService = Depends(get_auth_service),
) -> StandardResponse[TokenResponse]:
    """Handle the OAuth2 callback and return tokens."""
    return service.social_callback(code)
