from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_db
from app.services.cognito import cognito_service
from app.schemas.user import UserCreate, LoginRequest, TokenResponse, OTPRequest, OTPVerify, RefreshRequest, ForgotPasswordRequest, ForgotPasswordConfirm, ConfirmSignupRequest, ResendConfirmationRequest, UserResponse, PermissionsResponse
from app.models.user import User, Role
from app.utils.responses import StandardResponse, create_success_response
from app.api.v1.deps.security import get_current_user, get_user_permissions, require_permission, security
from app.utils.constants import SuccessMessages, ErrorMessages, UserRoles, UserPermissions, Defaults
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger
from botocore.exceptions import ClientError
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter()


@router.post("/signup", response_model=StandardResponse[UserResponse])
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new user. Requires email confirmation via /confirm-signup."""
    # Check if user exists
    stmt = select(User).where((User.email == user_in.email) | (User.phone_number == user_in.phone_number))
    if db.execute(stmt).first():
        api_logger.warning(format_log_message(LogMessages.Auth.SIGNUP_ATTEMPT_EXISTING, email=user_in.email))
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=ErrorMessages.USER_EXISTS,
        )
    
    try:
        # Cognito Signup (returns UserSub — we store it so /auth/me can find the user by token)
        cognito_response = cognito_service.signup(
            email=user_in.email,
            password=user_in.password,
            full_name=user_in.full_name,
            phone_number=user_in.phone_number
        )
        cognito_sub = cognito_response.get("UserSub")

        # Create user in DB with cognito_sub so login/me works
        db_user = User(
            email=user_in.email,
            full_name=user_in.full_name,
            phone_number=user_in.phone_number,
            is_active=True,
            cognito_sub=cognito_sub,
        )
        db.add(db_user)

        # Assign Registered User role
        stmt_role = select(Role).where(Role.name == UserRoles.REGISTERED_USER)
        role = db.execute(stmt_role).scalar_one_or_none()
        if role:
            db_user.roles.append(role)
            
        db.commit()
        db.refresh(db_user)
        
        return create_success_response(data=db_user, message=SuccessMessages.USER_REGISTERED)
    except Exception as e:
        db.rollback()
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)
        
@router.post("/signup/admin", response_model=StandardResponse[UserResponse], dependencies=[require_permission(UserPermissions.USER_CREATE)])
def signup_admin(
    user_in: UserCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Onboard an Admin user. Same payload as normal signup; assigns Admin role. Requires user:create (admin only)."""
    # Check if user exists
    stmt = select(User).where((User.email == user_in.email) | (User.phone_number == user_in.phone_number))
    if db.execute(stmt).first():
        api_logger.warning(format_log_message(LogMessages.Auth.SIGNUP_ATTEMPT_EXISTING, email=user_in.email))
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=ErrorMessages.USER_EXISTS,
        )
    
    try:
        # Cognito Signup (returns UserSub — store for /auth/me)
        cognito_response = cognito_service.signup(
            email=user_in.email,
            password=user_in.password,
            full_name=user_in.full_name,
            phone_number=user_in.phone_number
        )
        cognito_sub = cognito_response.get("UserSub")

        # Create user in DB with cognito_sub
        db_user = User(
            email=user_in.email,
            full_name=user_in.full_name,
            phone_number=user_in.phone_number,
            is_active=True,
            cognito_sub=cognito_sub,
        )
        db.add(db_user)

        # Assign Admin role
        stmt_role = select(Role).where(Role.name == UserRoles.ADMIN)
        role = db.execute(stmt_role).scalar_one_or_none()
        if role:
            db_user.roles.append(role)
            
        db.commit()
        db.refresh(db_user)
        
        return create_success_response(data=db_user, message=SuccessMessages.ADMIN_REGISTERED)
    except Exception as e:
        db.rollback()
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)

@router.post("/confirm-signup", response_model=StandardResponse[bool])
def confirm_signup(confirm_in: ConfirmSignupRequest, db: Session = Depends(get_db)):
    """Confirm sign-up with the code sent by Cognito. Marks email as verified in the app DB."""
    try:
        cognito_service.confirm_signup(confirm_in.email, confirm_in.code)
        # Update local user: email is now verified (Cognito confirmed it)
        stmt = select(User).where(User.email == confirm_in.email)
        user = db.execute(stmt).scalar_one_or_none()
        if user:
            user.is_email_verified = True
            db.commit()
        return create_success_response(data=True, message=SuccessMessages.ACCOUNT_CONFIRMED)
    except ClientError as e:
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)

@router.post("/resend-confirmation", response_model=StandardResponse[bool])
def resend_confirmation(req: ResendConfirmationRequest):
    """Resend the email confirmation code to the user."""
    try:
        cognito_service.resend_confirmation_code(req.email)
        return create_success_response(data=True, message=SuccessMessages.CONFIRMATION_CODE_SENT)
    except ClientError as e:
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)

@router.post("/login/password", response_model=StandardResponse[TokenResponse])
def login_password(login_in: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email or phone number + password. Returns access and refresh tokens."""
    # Resolve email or phone to user; Cognito username is always email (pool sign-in identifier)
    stmt = select(User).where((User.email == login_in.username) | (User.phone_number == login_in.username))
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
        api_logger.warning(format_log_message(LogMessages.Auth.LOGIN_FAILED, email=login_in.username, error=ErrorMessages.USER_NOT_FOUND))
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    cognito_username = user.email
    try:
        auth_result = cognito_service.login_password(cognito_username, login_in.password)
        return create_success_response(
            data=TokenResponse(
                access_token=auth_result["AccessToken"],
                refresh_token=auth_result.get("RefreshToken"),
                id_token=auth_result.get("IdToken"),
                expires_in=auth_result["ExpiresIn"]
            ),
            message=SuccessMessages.LOGIN_SUCCESSFUL
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "UserNotFoundException":
             raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
        if error_code == "UserNotConfirmedException":
             raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.USER_NOT_CONFIRMED)
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=ErrorMessages.INVALID_CREDENTIALS)
    except Exception:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=ErrorMessages.INVALID_CREDENTIALS)

@router.post("/login/otp/request", response_model=StandardResponse[dict])
def login_otp_request(otp_req: OTPRequest, db: Session = Depends(get_db)):
    """Request OTP for passwordless login (email or phone). Requires Cognito custom auth (Lambda).
    When client sends phone number, OTP can be sent via SMS if Lambda has SNS configured."""
    # Validate user exists in local DB; resolve to one user for Cognito
    stmt = select(User).where((User.email == otp_req.username) | (User.phone_number == otp_req.username))
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
         raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    # Cognito username is always email (pool sign-in identifier); Lambda gets userAttributes and can send SMS to phone_number
    cognito_username = user.email
    try:
        response = cognito_service.login_otp_request(cognito_username)
        return create_success_response(data={"session": response.get("Session")}, message=SuccessMessages.OTP_SENT)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = (e.response.get("Error") or {}).get("Message", str(e))
        if error_code == "UserNotFoundException":
             raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
        if error_code == "InvalidParameterException" and "Custom auth lambda trigger" in error_msg:
             raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.OTP_NOT_CONFIGURED)
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)
    except Exception as e:
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)

@router.post("/login/otp/verify", response_model=StandardResponse[TokenResponse])
def login_otp_verify(otp_ver: OTPVerify, db: Session = Depends(get_db)):
    """Verify OTP and return tokens. Requires session from /login/otp/request. username = same as request (email or phone)."""
    # Resolve username (email or phone) to Cognito username (email) so RespondToAuthChallenge succeeds
    stmt = select(User).where((User.email == otp_ver.username) | (User.phone_number == otp_ver.username))
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    cognito_username = user.email
    try:
        auth_result = cognito_service.login_otp_verify(otp_ver.session, cognito_username, otp_ver.code)
        return create_success_response(
            data=TokenResponse(
                access_token=auth_result["AccessToken"],
                refresh_token=auth_result.get("RefreshToken"),
                id_token=auth_result.get("IdToken"),
                expires_in=auth_result["ExpiresIn"]
            ),
            message=SuccessMessages.LOGIN_SUCCESSFUL
        )
    except Exception:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=ErrorMessages.INVALID_OTP)

@router.post("/refresh", response_model=StandardResponse[TokenResponse])
def refresh_token(body: RefreshRequest):
    """Refresh access token using refresh_token in request body.
    When Cognito app client has a secret, include username (sub or email) for SECRET_HASH."""
    settings = get_settings()
    if settings.cognito_client_secret and not (body.username or "").strip():
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.REFRESH_USERNAME_REQUIRED,
        )
    try:
        auth_result = cognito_service.refresh_token(body.refresh_token, (body.username or "").strip())
        return create_success_response(
            data=TokenResponse(
                access_token=auth_result["AccessToken"],
                id_token=auth_result.get("IdToken"),
                expires_in=auth_result["ExpiresIn"]
            )
        )
    except Exception:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=ErrorMessages.INVALID_TOKEN)

@router.post("/logout", response_model=StandardResponse[bool])
def logout(user: User = Depends(get_current_user), auth: HTTPAuthorizationCredentials = Depends(security)):
    """Invalidate the current user's Cognito session."""
    try:
        cognito_service.logout(auth.credentials)
        api_logger.info(format_log_message(LogMessages.Auth.LOGOUT_SUCCESS, email=user.email))
        return create_success_response(data=True, message=SuccessMessages.LOGOUT_SUCCESSFUL)
    except Exception as e:
        api_logger.error(format_log_message(LogMessages.Auth.LOGOUT_FAILED, error=str(e)))
        return create_success_response(data=False, message=ErrorMessages.LOGOUT_FAILED)

@router.post("/forgot-password/request", response_model=StandardResponse[bool])
def forgot_password_request(fp_req: ForgotPasswordRequest):
    """Send password reset code to the user's email."""
    try:
        cognito_service.forgot_password_request(fp_req.email)
        return create_success_response(data=True, message=SuccessMessages.OTP_SENT)
    except Exception as e:
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)

@router.post("/forgot-password/confirm", response_model=StandardResponse[bool])
def forgot_password_confirm(fp_conf: ForgotPasswordConfirm):
    """Confirm password reset with code and new password."""
    try:
        cognito_service.forgot_password_confirm(fp_conf.email, fp_conf.code, fp_conf.new_password)
        return create_success_response(data=True, message=SuccessMessages.PASSWORD_RESET_SUCCESS)
    except Exception as e:
        server_error = format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=server_error)

@router.get("/social-login", response_model=StandardResponse[dict])
def social_login(provider: str = "Google"):
    """Get the social login URL for a specific provider."""
    login_url = cognito_service.get_social_login_url(provider)
    return create_success_response(data={"url": login_url})

@router.get("/me", response_model=StandardResponse[UserResponse])
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return create_success_response(data=current_user, message=None)


@router.get("/me/permissions", response_model=StandardResponse[PermissionsResponse])
def get_current_user_permissions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the current user's permission codes (from roles and inherited assignments)."""
    perms = sorted(get_user_permissions(current_user, db))
    return create_success_response(data=PermissionsResponse(permissions=perms), message=None)


@router.get("/callback", response_model=StandardResponse[TokenResponse])
def social_callback(code: str, db: Session = Depends(get_db)):
    """Handle the OAuth2 callback and return tokens."""
    try:
        auth_result = cognito_service.exchange_code_for_tokens(code)
        id_token = auth_result.get("id_token")
        
        # Verify the token to get user info
        payload = cognito_service.verify_token(id_token)
        if not payload:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=ErrorMessages.SOCIAL_AUTH_FAILED)
            
        email = payload.get("email")
        cognito_sub = payload.get("sub")
        full_name = payload.get("name", Defaults.SOCIAL_USER_DEFAULT_NAME)
        
        # Check if user exists in local DB
        stmt = select(User).where((User.cognito_sub == cognito_sub) | (User.email == email))
        user = db.execute(stmt).scalar_one_or_none()
        
        if not user:
            # Auto-register social user
            user = User(
                email=email,
                full_name=full_name,
                cognito_sub=cognito_sub,
                phone_number=f"social_{cognito_sub[:10]}", # Place holder for social users if phone is mandatory in unique constraint
                is_active=True
            )
            db.add(user)
            
            # Assign default role
            stmt_role = select(Role).where(Role.name == UserRoles.REGISTERED_USER)
            role = db.execute(stmt_role).scalar_one_or_none()
            if role:
                user.roles.append(role)
                
            db.commit()
            db.refresh(user)
            api_logger.info(format_log_message(LogMessages.Auth.SOCIAL_LOGIN_SUCCESS, email=email))
        elif not user.cognito_sub:
            # Link existing local user to social account
            user.cognito_sub = cognito_sub
            db.commit()
            db.refresh(user)
            
        return create_success_response(
            data=TokenResponse(
                access_token=auth_result["access_token"],
                refresh_token=auth_result.get("refresh_token"),
                id_token=auth_result.get("id_token"),
                expires_in=auth_result["expires_in"]
            ),
            message=SuccessMessages.SOCIAL_LOGIN_SUCCESSFUL
        )
    except Exception as e:
        api_logger.error(format_log_message(LogMessages.Auth.SOCIAL_AUTH_FAILED_LOG, email=LogMessages.Auth.UNKNOWN_EMAIL, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.SOCIAL_AUTH_FAILED)
