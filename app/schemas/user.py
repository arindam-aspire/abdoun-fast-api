import uuid
import re
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.constants import ValidationMessages

# E.164 phone format for validation reuse
PHONE_E164_REGEX = r"^\+[1-9]\d{1,14}$"

class PermissionBase(BaseModel):
    code: str
    description: Optional[str] = None

class PermissionResponse(PermissionBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleResponse(RoleBase):
    id: uuid.UUID
    permissions: List[PermissionResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.PHONE_E164)
        return v

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError(ValidationMessages.PASSWORD_MIN_LENGTH)
        if not any(c.isupper() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_UPPERCASE)
        if not any(c.islower() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_LOWERCASE)
        if not any(c.isdigit() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_NUMBER)
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in v):
            raise ValueError(ValidationMessages.PASSWORD_SPECIAL)
        return v

class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    is_email_verified: bool
    is_phone_verified: bool
    roles: List[RoleResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int

class LoginRequest(BaseModel):
    username: str # email or phone
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if "@" in v:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
                raise ValueError(ValidationMessages.INVALID_EMAIL_FORMAT)
            return v
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.USERNAME_EMAIL_OR_PHONE)
        return v

class OTPRequest(BaseModel):
    username: str  # email or phone (E.164 for phone)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if "@" in v:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
                raise ValueError(ValidationMessages.INVALID_EMAIL_FORMAT)
            return v
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.USERNAME_EMAIL_OR_E164)
        return v


class RefreshRequest(BaseModel):
    refresh_token: str
    # Required when Cognito app client has a secret (for SECRET_HASH). Use sub or email from login/id_token.
    username: Optional[str] = None

class OTPVerify(BaseModel):
    username: str  # email or phone (E.164); same as in /login/otp/request
    code: str
    session: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if "@" in v:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
                raise ValueError(ValidationMessages.INVALID_EMAIL_FORMAT)
            return v
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.USERNAME_EMAIL_OR_E164)
        return v

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ConfirmSignupRequest(BaseModel):
    email: EmailStr
    code: str

class ResendConfirmationRequest(BaseModel):
    email: EmailStr

class ForgotPasswordConfirm(BaseModel):
    email: EmailStr
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError(ValidationMessages.PASSWORD_MIN_LENGTH)
        if not any(c.isupper() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_UPPERCASE)
        if not any(c.islower() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_LOWERCASE)
        if not any(c.isdigit() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_NUMBER)
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in v):
            raise ValueError(ValidationMessages.PASSWORD_SPECIAL)
        return v

class AgentInviteRequest(BaseModel):
    email: EmailStr

class AgentRegister(BaseModel):
    full_name: str
    phone_number: str
    service_area: str
    token: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.PHONE_E164)
        return v


class AdminAgentAssignmentRequest(BaseModel):
    admin_id: uuid.UUID
    agent_id: uuid.UUID
    can_inherit_privileges: bool = True


# --- User Management (Admin) ---

class UserUpdate(BaseModel):
    """Partial update for user. All fields optional."""
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.PHONE_E164)
        return v


class RoleAssignmentRequest(BaseModel):
    """Request body for assigning a role to a user."""
    role_id: uuid.UUID


class PermissionsResponse(BaseModel):
    """List of permission codes for the current user."""
    permissions: List[str]
