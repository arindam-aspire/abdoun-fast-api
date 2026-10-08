from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSessionDep, RequestContext, RequestContextDep, require_authenticated_user
from app.schemas.auth import (
    ChangePasswordRequest,
    ConfirmSignUpRequest,
    ForgotPasswordRequest,
    ProfilePictureUploadRequest,
    ProfileUpdateRequest,
    ProfileUpdateVerifyRequest,
    RefreshTokenRequest,
    ResendConfirmationRequest,
    ResetPasswordRequest,
    SendPhoneOtpRequest,
    SignInRequest,
    SignInWithOtpRequest,
    SignInWithOtpVerifyRequest,
    SignUpRequest,
    SocialLoginRequest,
    VerifyPhoneOtpRequest,
)
from app.services.auth import (
    authenticate_password,
    build_otp_response_data,
    build_otp_response_meta,
    cognito_service,
    confirm_signup_user,
    create_auth_tokens,
    create_otp_challenge,
    ensure_agent_can_authenticate,
    find_user_by_username,
    get_user_or_404,
    mark_password_set,
    normalize_username,
    otp_delivery_message,
    register_signup_user,
    resend_signup_confirmation,
    send_dev_otp,
    serialize_user,
    verify_otp_challenge,
    verify_refresh_token,
)
from app.core.security import hash_secret, verify_secret
from app.services.social_auth import authenticate_social, exchange_cognito_authorization_code
from app.services.phone_verification import (
    PHONE_VERIFY_PURPOSE,
    apply_profile_phone_number,
    begin_profile_phone_change,
    complete_profile_phone_verification,
    confirm_phone_otp,
    issue_signup_phone_otp,
    request_phone_otp,
)
from app.services.media_urls import local_media_url
from app.utils.api_response import success_response
from app.utils.status_codes import (
    STATUS_BAD_REQUEST,
    STATUS_NOT_FOUND,
    STATUS_SERVICE_UNAVAILABLE,
    STATUS_UNAUTHORIZED,
)

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.post("/login/password")
def login_with_password(payload: SignInRequest, db: DBSessionDep) -> dict:
    user = authenticate_password(
        db,
        username=payload.username,
        password=payload.password,
    )
    tokens = create_auth_tokens(db, user)
    db.commit()
    return success_response(
        tokens,
        "Signed in successfully",
    )


@router.post("/login/social")
def login_with_social(payload: SocialLoginRequest, db: DBSessionDep) -> dict:
    """Sign in, or create, a User or Owner account from a validated Cognito identity."""
    id_token = payload.id_token
    access_token = payload.access_token
    if (payload.code or "").strip():
        id_token = exchange_cognito_authorization_code(
            code=payload.code or "",
            code_verifier=payload.code_verifier or "",
            redirect_uri=payload.redirect_uri or "",
        )
        access_token = None
    user, role_name = authenticate_social(
        db,
        provider=payload.provider,
        id_token=id_token,
        access_token=access_token,
        role=payload.role,
    )
    tokens = create_auth_tokens(db, user, role_name=role_name)
    db.commit()
    return success_response(tokens, "Signed in successfully")


@router.post("/login/otp/request")
def login_with_otp_request(payload: SignInWithOtpRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.username)
    if not user or not user.is_active:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid account")
    ensure_agent_can_authenticate(db, user)

    challenge, otp = create_otp_challenge(
        db,
        user=user,
        purpose="login_otp",
        new_value=normalize_username(payload.username),
    )
    send_dev_otp(
        user=user,
        purpose="login",
        otp=otp,
        challenge=challenge,
        identifier=payload.username,
    )
    db.commit()
    return success_response(
        build_otp_response_data(session=str(challenge.id)),
        otp_delivery_message(
            fallback_dev_message="OTP sent successfully",
            sent_message="OTP sent successfully",
        ),
    )


@router.post("/login/otp/verify")
def login_with_otp_verify(payload: SignInWithOtpVerifyRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.username)
    if not user or not user.is_active:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid account")
    ensure_agent_can_authenticate(db, user)

    try:
        challenge_id = UUID(payload.session)
    except ValueError as exc:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid OTP session") from exc

    verify_otp_challenge(
        db,
        purpose="login_otp",
        code=payload.code,
        user=user,
        challenge_id=challenge_id,
        new_value=normalize_username(payload.username),
    )
    return success_response(
        create_auth_tokens(db, user),
        "Signed in successfully",
    )


@router.post("/signup")
def sign_up(payload: SignUpRequest, db: DBSessionDep) -> dict:
    user = register_signup_user(
        db,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password=payload.password,
        role=payload.role,
    )
    has_phone = isinstance(user.phone_number, str) and bool(user.phone_number.strip())
    challenge, otp = create_otp_challenge(
        db,
        user=user,
        purpose="signup_confirm",
        new_value=normalize_username(user.email),
        supersede=True,
        avoid_purposes=(PHONE_VERIFY_PURPOSE,),
    )
    delivered = send_dev_otp(
        user=user,
        purpose="signup",
        otp=otp,
        challenge=challenge,
        skip_sms=True,
    )
    if delivered is False:
        raise HTTPException(status_code=STATUS_SERVICE_UNAVAILABLE, detail="Unable to send verification code")
    if has_phone:
        issue_signup_phone_otp(db, user=user, excluded_otps={otp})
    db.commit()
    phone_pending = isinstance(user.phone_number, str) and bool(user.phone_number.strip()) and user.is_phone_verified is not True
    return success_response(
        build_otp_response_data(
            **({"phone_verification_required": True} if phone_pending else {}),
        ),
        otp_delivery_message(
            fallback_dev_message="Account created. Verification code sent.",
            sent_message="Account created. Verification code sent.",
        ),
    )


@router.post("/confirm-signup")
def confirm_sign_up(payload: ConfirmSignUpRequest, db: DBSessionDep) -> dict:
    user = confirm_signup_user(
        db,
        email=payload.email,
        code=payload.code,
        phone_number=payload.phone_number,
        phone_otp=payload.phone_otp,
    )
    db.commit()
    phone_pending = isinstance(user.phone_number, str) and bool(user.phone_number.strip()) and user.is_phone_verified is not True
    email_verified = user.is_email_verified is True
    phone_verified = user.is_phone_verified is True
    if email_verified and phone_verified:
        message = "Account verified successfully"
    elif email_verified and phone_pending:
        message = "Email verified. Mobile verification is still required"
    elif phone_verified and not email_verified:
        message = "Mobile number verified. Email verification is still required"
    elif user.is_active:
        message = "Account verified successfully"
    else:
        message = "Verification successful"
    return success_response(
        {
            "verified": user.is_active is True,
            "email_verified": user.is_email_verified is True,
            "phone_verified": user.is_phone_verified is True,
        },
        message,
    )


@router.post("/send-phone-otp")
def send_phone_otp(payload: SendPhoneOtpRequest, context: RequestContextDep, db: DBSessionDep) -> dict:
    data, message = request_phone_otp(db, user_id=context.user_id, phone_number=payload.phone_number)
    db.commit()
    return success_response(build_otp_response_data(**data), message)


@router.post("/resend-phone-otp")
def resend_phone_otp(payload: SendPhoneOtpRequest, context: RequestContextDep, db: DBSessionDep) -> dict:
    data, message = request_phone_otp(db, user_id=context.user_id, phone_number=payload.phone_number)
    db.commit()
    return success_response(build_otp_response_data(**data), message)


@router.post("/verify-phone-otp")
def verify_phone_otp(payload: VerifyPhoneOtpRequest, context: RequestContextDep, db: DBSessionDep) -> dict:
    user = confirm_phone_otp(
        db,
        user_id=context.user_id,
        phone_number=payload.phone_number,
        phone_otp=payload.phone_otp,
    )
    db.commit()
    return success_response(
        {"verified": True, "phone_verified": user.is_phone_verified is True},
        "Mobile number verified successfully",
    )


@router.post("/resend-confirmation")
def resend_confirmation(payload: ResendConfirmationRequest, db: DBSessionDep) -> dict:
    resend_signup_confirmation(db, email=payload.email, channel=payload.channel)
    db.commit()
    return success_response(
        build_otp_response_data(),
        otp_delivery_message(
            fallback_dev_message="Verification code sent.",
            sent_message="Verification code sent.",
        ),
    )


@router.get("/me")
def get_me(context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    return success_response(serialize_user(db, user))


@router.patch("/me")
def update_me(payload: ProfileUpdateRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    if payload.email is not None:
        user.email = normalize_username(payload.email)
        user.is_email_verified = False
    if payload.phone_number is not None:
        apply_profile_phone_number(db, user=user, phone_number=payload.phone_number)
    db.commit()
    db.refresh(user)
    return success_response(serialize_user(db, user), "Profile updated successfully")


@router.patch("/me/profile/request")
def request_profile_update(payload: ProfileUpdateRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    fields: list[str] = []

    if payload.email:
        email_challenge, dev_email_otp = create_otp_challenge(
            db,
            user=user,
            purpose="profile_email",
            new_value=normalize_username(payload.email),
        )
        send_dev_otp(
            user=user,
            purpose="profile",
            otp=dev_email_otp,
            challenge=email_challenge,
        )
        fields.append("email")
    if payload.phone_number and begin_profile_phone_change(db, user=user, phone_number=payload.phone_number):
        fields.append("phone_number")

    db.commit()
    return success_response(
        build_otp_response_data(
            message=otp_delivery_message(
                fallback_dev_message="Verification code logged in dev mode.",
                sent_message="Verification code sent.",
            ),
            requires_verification=bool(fields),
            verification_fields=fields,
        ),
        "Verification required" if fields else "No verification required",
    )


@router.post("/me/profile/verify")
def verify_profile_update(payload: ProfileUpdateVerifyRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    if payload.email and payload.email_otp:
        verify_otp_challenge(
            db,
            purpose="profile_email",
            code=payload.email_otp,
            user=user,
            new_value=normalize_username(payload.email),
        )
        user.email = normalize_username(payload.email)
        user.is_email_verified = True
    elif payload.phone_number and payload.phone_otp:
        complete_profile_phone_verification(
            db,
            user=user,
            phone_number=payload.phone_number,
            phone_otp=payload.phone_otp,
        )
    else:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Verification payload is incomplete")

    db.commit()
    return success_response({"message": "Profile updated successfully"}, "Profile updated successfully")


@router.post("/me/profile-picture")
def request_profile_picture_upload(payload: ProfilePictureUploadRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    user.profile_picture_url = local_media_url(f"profile-pictures/{user.id}/{payload.file_name}")
    db.commit()
    return success_response({"upload_url": user.profile_picture_url}, "Profile picture upload URL generated")


@router.delete("/me/profile-picture")
def delete_profile_picture(context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    user.profile_picture_url = None
    db.commit()
    db.refresh(user)
    return success_response(serialize_user(db, user), "Profile picture removed")


@router.post("/forgot-password/request")
def forgot_password(payload: ForgotPasswordRequest, db: DBSessionDep) -> dict:
    username = payload.email or "".join(filter(None, [payload.phoneCountryCode, payload.phoneNationalNumber]))
    user = find_user_by_username(db, username) if username else None
    if user:
        if cognito_service.enabled and (user.cognito_sub or user.is_email_verified):
            try:
                cognito_service.forgot_password(email=user.email)
                db.commit()
                return success_response(
                    True,
                    otp_delivery_message(
                        fallback_dev_message="If the account exists, a verification code has been sent",
                        sent_message="If the account exists, a verification code has been sent",
                    ),
                )
            except HTTPException:
                pass
        challenge, otp = create_otp_challenge(
            db,
            user=user,
            purpose="reset_password",
            new_value=normalize_username(user.email),
        )
        send_dev_otp(user=user, purpose="password reset", otp=otp, challenge=challenge)
        db.commit()
        return success_response(
            True,
            otp_delivery_message(
                fallback_dev_message="Verification code logged in dev mode",
                sent_message="If the account exists, a verification code has been sent",
            ),
            build_otp_response_meta(),
        )
    return success_response(True, "If the account exists, a verification code has been sent")


@router.post("/forgot-password/confirm")
def reset_password(payload: ResetPasswordRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.email)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Account not found")
    if cognito_service.enabled:
        try:
            cognito_service.confirm_forgot_password(
                email=user.email,
                code=payload.code,
                new_password=payload.new_password,
            )
            user.password_hash = hash_secret(payload.new_password)
            mark_password_set(db, user)
            db.commit()
            return success_response({"updated": True}, "Password reset successfully")
        except HTTPException as exc:
            if user.cognito_sub:
                raise
            if exc.status_code not in {STATUS_BAD_REQUEST, STATUS_UNAUTHORIZED}:
                raise
    verify_otp_challenge(
        db,
        purpose="reset_password",
        code=payload.code,
        user=user,
        new_value=normalize_username(user.email),
    )
    user.password_hash = hash_secret(payload.new_password)
    if user.cognito_sub and cognito_service.enabled:
        cognito_service.admin_set_password(email=user.email, password=payload.new_password)
    mark_password_set(db, user)
    db.commit()
    return success_response({"updated": True}, "Password reset successfully")


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    if not user.password_hash or not verify_secret(payload.previous_password, user.password_hash):
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Current password is invalid")
    user.password_hash = hash_secret(payload.password)
    if user.cognito_sub and cognito_service.enabled:
        cognito_service.admin_set_password(email=user.email, password=payload.password)
    mark_password_set(db, user)
    db.commit()
    return success_response({"updated": True}, "Password changed successfully")


@router.post("/refresh")
def refresh(payload: RefreshTokenRequest, db: DBSessionDep) -> dict:
    if not payload.refresh_token:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Refresh token is required")
    user = verify_refresh_token(db, payload.refresh_token, payload.username)
    return success_response(create_auth_tokens(db, user), "Token refreshed")


@router.post("/logout")
def logout() -> dict:
    return success_response({"logged_out": True}, "Logged out successfully")
