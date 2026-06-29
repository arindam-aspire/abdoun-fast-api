from __future__ import annotations

from pydantic import BaseModel, Field


class SignInRequest(BaseModel):
    username: str
    password: str
    rememberMe: bool = False


class SignInWithOtpRequest(BaseModel):
    username: str


class SignInWithOtpVerifyRequest(BaseModel):
    username: str
    code: str
    session: str


class SignUpRequest(BaseModel):
    full_name: str
    email: str
    phone_number: str | None = None
    password: str
    role: str


class ConfirmSignUpRequest(BaseModel):
    email: str
    code: str


class ForgotPasswordRequest(BaseModel):
    email: str | None = None
    phoneCountryCode: str | None = None
    phoneNationalNumber: str | None = None


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    password: str
    previous_password: str


class RefreshTokenRequest(BaseModel):
    username: str
    refresh_token: str | None = None


class ProfileUpdateRequest(BaseModel):
    email: str | None = None
    phone_number: str | None = None


class ProfileUpdateVerifyRequest(BaseModel):
    email: str | None = None
    email_otp: str | None = None
    phone_number: str | None = None
    phone_otp: str | None = None


class ProfilePictureUploadRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int = Field(ge=0)
