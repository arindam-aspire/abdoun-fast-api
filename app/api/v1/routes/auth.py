from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.schemas.auth import (
    ChangePasswordRequest,
    ConfirmSignUpRequest,
    ForgotPasswordRequest,
    ProfilePictureUploadRequest,
    ProfileUpdateRequest,
    ProfileUpdateVerifyRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SignInRequest,
    SignInWithOtpRequest,
    SignInWithOtpVerifyRequest,
    SignUpRequest,
)
from app.services.auth import (
    authenticate_password,
    create_auth_tokens,
    create_otp_challenge,
    create_user,
    find_user_by_username,
    get_user_or_404,
    normalize_username,
    resolve_effective_sign_in_role,
    send_dev_otp,
    serialize_user,
    verify_otp_challenge,
    verify_refresh_token,
)
from app.core.security import hash_secret, verify_secret
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_NOT_FOUND, STATUS_UNAUTHORIZED

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.post("/login/password")
def login_with_password(payload: SignInRequest, db: DBSessionDep) -> dict:
    user = authenticate_password(
        db,
        username=payload.username,
        password=payload.password,
        role=payload.role,
    )
    effective_role = resolve_effective_sign_in_role(db, user=user, requested_role=payload.role)
    return success_response(
        create_auth_tokens(db, user, effective_role),
        "Signed in successfully",
    )


@router.post("/login/otp/request")
def login_with_otp_request(payload: SignInWithOtpRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.username)
    if not user or not user.is_active:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid account")
    try:
        resolve_effective_sign_in_role(db, user=user, requested_role=payload.role)
    except HTTPException as exc:
        if exc.status_code == STATUS_FORBIDDEN:
            raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid account") from exc
        raise

    challenge, otp = create_otp_challenge(
        db,
        user=user,
        purpose="login_otp",
        new_value=normalize_username(payload.username),
    )
    send_dev_otp(user=user, purpose="login", otp=otp)
    db.commit()
    return success_response(
        {"session": str(challenge.id), "otp": otp},
        "OTP sent successfully",
    )


@router.post("/login/otp/verify")
def login_with_otp_verify(payload: SignInWithOtpVerifyRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.username)
    if not user or not user.is_active:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid account")
    try:
        effective_role = resolve_effective_sign_in_role(db, user=user, requested_role=payload.role)
    except HTTPException as exc:
        if exc.status_code == STATUS_FORBIDDEN:
            raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid account") from exc
        raise

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
        create_auth_tokens(db, user, effective_role),
        "Signed in successfully",
    )


@router.post("/signup")
def sign_up(payload: SignUpRequest, db: DBSessionDep) -> dict:
    user = create_user(
        db,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password=payload.password,
        role=payload.role,
    )
    _, otp = create_otp_challenge(
        db,
        user=user,
        purpose="signup_confirm",
        new_value=normalize_username(payload.email),
    )
    send_dev_otp(user=user, purpose="signup", otp=otp)
    db.commit()
    return success_response(
        {"otp": otp, "dev_email_otp": otp},
        "Account created. Verification code logged in dev mode.",
    )


@router.post("/confirm-signup")
def confirm_sign_up(payload: ConfirmSignUpRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.email)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Account not found")

    verify_otp_challenge(
        db,
        purpose="signup_confirm",
        code=payload.code,
        user=user,
        new_value=normalize_username(payload.email),
    )
    user.is_email_verified = True
    db.commit()
    return success_response({"verified": True}, "Account verified successfully")


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
        user.phone_number = payload.phone_number
        user.is_phone_verified = False
    db.commit()
    db.refresh(user)
    return success_response(serialize_user(db, user), "Profile updated successfully")


@router.patch("/me/profile/request")
def request_profile_update(payload: ProfileUpdateRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    dev_email_otp = None
    dev_phone_otp = None
    fields: list[str] = []

    if payload.email:
        _, dev_email_otp = create_otp_challenge(
            db,
            user=user,
            purpose="profile_email",
            new_value=normalize_username(payload.email),
        )
        fields.append("email")
    if payload.phone_number:
        _, dev_phone_otp = create_otp_challenge(
            db,
            user=user,
            purpose="profile_phone",
            new_value=payload.phone_number,
        )
        fields.append("phone_number")

    if dev_email_otp or dev_phone_otp:
        send_dev_otp(user=user, purpose="profile", otp=dev_email_otp or dev_phone_otp or "")

    db.commit()
    return success_response(
        {
            "message": "Verification code logged in dev mode.",
            "requires_verification": bool(fields),
            "verification_fields": fields,
            "dev_phone_otp": dev_phone_otp,
            "dev_email_otp": dev_email_otp,
            "otp": dev_email_otp or dev_phone_otp,
        },
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
        verify_otp_challenge(
            db,
            purpose="profile_phone",
            code=payload.phone_otp,
            user=user,
            new_value=payload.phone_number,
        )
        user.phone_number = payload.phone_number
        user.is_phone_verified = True
    else:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Verification payload is incomplete")

    db.commit()
    return success_response({"message": "Profile updated successfully"}, "Profile updated successfully")


@router.post("/me/profile-picture")
def request_profile_picture_upload(payload: ProfilePictureUploadRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    user.profile_picture_url = f"dev://profile-pictures/{user.id}/{payload.file_name}"
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
        _, otp = create_otp_challenge(
            db,
            user=user,
            purpose="reset_password",
            new_value=normalize_username(user.email),
        )
        send_dev_otp(user=user, purpose="password reset", otp=otp)
        db.commit()
        return success_response(True, "Verification code logged in dev mode", {"otp": otp})
    return success_response(True, "If the account exists, a verification code has been sent")


@router.post("/forgot-password/confirm")
def reset_password(payload: ResetPasswordRequest, db: DBSessionDep) -> dict:
    user = find_user_by_username(db, payload.email)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Account not found")
    verify_otp_challenge(
        db,
        purpose="reset_password",
        code=payload.code,
        user=user,
        new_value=normalize_username(user.email),
    )
    user.password_hash = hash_secret(payload.new_password)
    db.commit()
    return success_response({"updated": True}, "Password reset successfully")


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    if not user.password_hash or not verify_secret(payload.previous_password, user.password_hash):
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Current password is invalid")
    user.password_hash = hash_secret(payload.password)
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
