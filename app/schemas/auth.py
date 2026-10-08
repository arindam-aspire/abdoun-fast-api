from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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


class SocialLoginRequest(BaseModel):
    """Provider assertion for User or Owner social sign-in and sign-up.

    The website sends the Cognito authorization `code` from the hosted-UI
    callback. A Cognito ID token in `id_token` remains accepted. Direct Google
    and Facebook tokens are not accepted. Profile fields are taken from the
    validated token. A requested role is accepted only when it is User or
    Owner. An existing account keeps the role stored in the database.
    """

    provider: str
    id_token: str | None = None
    access_token: str | None = None
    code: str | None = None
    code_verifier: str | None = None
    redirect_uri: str | None = None
    role: str | None = None

    @model_validator(mode="after")
    def require_provider_assertion(self) -> "SocialLoginRequest":
        if not (self.provider or "").strip():
            raise ValueError("A social provider is required")
        has_token = bool((self.id_token or "").strip() or (self.access_token or "").strip())
        has_code = bool(
            (self.code or "").strip()
            and (self.code_verifier or "").strip()
            and (self.redirect_uri or "").strip()
        )
        if not has_token and not has_code:
            raise ValueError("A provider token is required")
        return self


class ConfirmSignUpRequest(BaseModel):
    email: str | None = None
    code: str | None = None
    email_otp: str | None = None
    phone_number: str | None = None
    phone_otp: str | None = None

    @model_validator(mode="after")
    def require_signup_verification(self) -> "ConfirmSignUpRequest":
        if self.email_otp and not self.code:
            self.code = self.email_otp
        has_identity = bool((self.email or "").strip() or (self.phone_number or "").strip())
        has_code = bool((self.code or "").strip() or (self.phone_otp or "").strip())
        if not has_identity or not has_code:
            raise ValueError("Email or mobile verification code is required")
        return self


class ResendConfirmationRequest(BaseModel):
    email: str


class SendPhoneOtpRequest(BaseModel):
    phone_number: str | None = None


class VerifyPhoneOtpRequest(BaseModel):
    phone_number: str
    phone_otp: str


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
