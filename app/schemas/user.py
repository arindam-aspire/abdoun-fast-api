"""Pydantic schemas for auth, user, role, permission, and agent API request/response."""
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.constants import AgentStatus, Defaults, ValidationMessages


class AgentStatusEnum(str, Enum):
    """Enum for agent status fields used in schemas."""
    INVITED = AgentStatus.INVITED
    PENDING_REVIEW = AgentStatus.PENDING_REVIEW
    APPROVED = AgentStatus.APPROVED
    DECLINED = AgentStatus.DECLINED
    ACTIVE = AgentStatus.ACTIVE
    INACTIVE = AgentStatus.INACTIVE
    DELETED = AgentStatus.DELETED

# E.164 phone format for validation reuse
PHONE_E164_REGEX = r"^\+[1-9]\d{1,14}$"


def _normalize_phone(value: str) -> str:
    """Strip and normalize to digits with leading + for E.164."""
    v = value.strip()
    if v.startswith("+"):
        digits = re.sub(r"\D", "", v[1:])
        return f"+{digits}"
    return re.sub(r"\D", "", v)

class PermissionBase(BaseModel):
    """Base fields for permission (code, description)."""
    code: str
    description: Optional[str] = None


class PermissionResponse(PermissionBase):
    """Permission with id and created_at (from DB)."""
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleResponse(RoleBase):
    """Role with id, permissions, created_at (from DB)."""
    id: uuid.UUID
    permissions: List[PermissionResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class UserBase(BaseModel):
    """Base user fields (email, full_name, phone_number) with E.164 phone validation."""
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized

class UserCreate(UserBase):
    """Request body for user registration (email, full_name, phone, password)."""
    phone_number: str = Field(..., description="Required for registration")
    password: str = Field(..., min_length=Defaults.PASSWORD_MIN_LENGTH)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < Defaults.PASSWORD_MIN_LENGTH:
            raise ValueError(ValidationMessages.PASSWORD_MIN_LENGTH)
        if not any(c.isupper() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_UPPERCASE)
        if not any(c.islower() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_LOWERCASE)
        if not any(c.isdigit() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_NUMBER)
        if not any(c in ValidationMessages.PASSWORD_SPECIAL_CHARS for c in v):
            raise ValueError(ValidationMessages.PASSWORD_SPECIAL)
        return v


class UserResponse(UserBase):
    """User profile response with roles and verification flags."""
    id: uuid.UUID
    is_active: bool
    is_email_verified: bool
    is_phone_verified: bool
    roles: List[RoleResponse] = []
    created_at: datetime
    requires_password_set: bool = Field(False, description="True if user must set a password (e.g. agent who signed in via OTP and has not set one)")

    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int
    # In response body only (not in JWT). True = first-time agent without password; show set-password UI.
    requires_password_set: bool = Field(False, description="True if user must set a password (e.g. agent who signed in via OTP and has not set one)")

class LoginRequest(BaseModel):
    """Login request (username = email or phone, password)."""
    username: str  # email or phone
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if "@" in v:
            if not re.match(ValidationMessages.EMAIL_REGEX_PATTERN, v):
                raise ValueError(ValidationMessages.INVALID_EMAIL_FORMAT)
            return v
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.USERNAME_EMAIL_OR_PHONE)
        return normalized


class OTPRequest(BaseModel):
    """Request OTP for passwordless login (username = email or E.164 phone)."""
    username: str  # email or phone (E.164 for phone)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if "@" in v:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
                raise ValueError(ValidationMessages.INVALID_EMAIL_FORMAT)
            return v
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.USERNAME_EMAIL_OR_E164)
        return normalized


class RefreshRequest(BaseModel):
    """Refresh token request (refresh_token; optional username for SECRET_HASH)."""
    refresh_token: str
    # Required when Cognito app client has a secret (for SECRET_HASH). Use sub or email from login/id_token.
    username: Optional[str] = None

class OTPVerify(BaseModel):
    """Verify OTP (username, code, session from /login/otp/request)."""
    username: str  # email or phone (E.164); same as in /login/otp/request
    code: str
    session: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if "@" in v:
            if not re.match(ValidationMessages.EMAIL_REGEX_PATTERN, v):
                raise ValueError(ValidationMessages.INVALID_EMAIL_FORMAT)
            return v
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.USERNAME_EMAIL_OR_E164)
        return normalized


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
        if len(v) < Defaults.PASSWORD_MIN_LENGTH:
            raise ValueError(ValidationMessages.PASSWORD_MIN_LENGTH)
        if not any(c.isupper() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_UPPERCASE)
        if not any(c.islower() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_LOWERCASE)
        if not any(c.isdigit() for c in v):
            raise ValueError(ValidationMessages.PASSWORD_NUMBER)
        if not any(c in ValidationMessages.PASSWORD_SPECIAL_CHARS for c in v):
            raise ValueError(ValidationMessages.PASSWORD_SPECIAL)
        return v


class SetPasswordRequest(BaseModel):
    """Request schema for setting initial password (for agents without password)."""
    password: str = Field(..., min_length=8)
    previous_password: Optional[str] = Field(None, description="Required only if user already has a password")

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

class AgentRegister(BaseModel):
    """Agent self-registration (full_name, phone, service_area, token)."""
    full_name: str
    phone_number: str
    service_area: str
    token: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized


class AdminCreateAgentRequest(BaseModel):
    """Admin: directly create an agent with a temporary password."""
    fullName: str = Field(..., min_length=1)
    email: EmailStr
    phone: str
    serviceArea: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized


class AdminCreateAgentResponse(BaseModel):
    """Response after admin directly creates an agent with a temporary password."""
    id: uuid.UUID
    email: str
    fullName: str
    phone: str
    serviceArea: str
    status: AgentStatusEnum
    temporaryPassword: str


class AdminAgentAssignmentRequest(BaseModel):
    """Request to assign an agent to the current authenticated admin."""
    agent_id: uuid.UUID
    can_inherit_privileges: bool = True


class AdminAgentAssignmentResponse(BaseModel):
    """Response model for admin-agent assignment details."""
    id: uuid.UUID
    admin_id: uuid.UUID
    admin_email: str
    admin_name: str
    agent_id: uuid.UUID
    agent_email: str
    agent_name: str
    is_active: bool
    can_inherit_privileges: bool
    assigned_at: datetime
    revoked_at: Optional[datetime] = None
    status: str  # See `app.utils.constants.AgentAssignmentStatus` (not an AgentStatus enum)

    model_config = {"from_attributes": True}


# --- Agent Onboarding Schemas ---

class AgentInviteRequest(BaseModel):
    """Request to invite an agent (admin endpoint)"""
    email: EmailStr


class AgentInviteResponse(BaseModel):
    """Response after inviting an agent"""
    id: uuid.UUID
    email: str
    status: AgentStatusEnum
    inviteLink: str
    invitedAt: datetime
    invitedBy: Optional[str] = None

    model_config = {"from_attributes": True}


class AgentOnboardingFormRequest(BaseModel):
    """Request to submit agent onboarding form"""
    fullName: str = Field(..., min_length=1)
    phone: str
    serviceArea: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized


class AgentOnboardingFormResponse(BaseModel):
    """Response after submitting onboarding form"""
    email: str
    status: AgentStatusEnum
    formSubmittedAt: datetime

    model_config = {"from_attributes": True}


class AgentValidateInviteResponse(BaseModel):
    """Response when validating invite token"""
    email: str
    status: AgentStatusEnum
    alreadySubmitted: bool


class AgentListResponse(BaseModel):
    """Agent list item response"""
    id: uuid.UUID
    email: str
    fullName: Optional[str] = None
    phone: Optional[str] = None
    serviceArea: Optional[str] = None
    status: AgentStatusEnum
    invitedAt: Optional[datetime] = None
    invitedBy: Optional[str] = None
    formSubmittedAt: Optional[datetime] = None
    reviewedAt: Optional[datetime] = None
    declineReason: Optional[str] = None

    model_config = {"from_attributes": True}


class AgentDetailResponse(BaseModel):
    """Detailed agent response"""
    id: uuid.UUID
    email: str
    fullName: Optional[str] = None
    phone: Optional[str] = None
    serviceArea: Optional[str] = None
    status: AgentStatusEnum
    invitedAt: Optional[datetime] = None
    invitedBy: Optional[str] = None
    formSubmittedAt: Optional[datetime] = None
    reviewedAt: Optional[datetime] = None
    reviewedBy: Optional[uuid.UUID] = None
    declineReason: Optional[str] = None
    passwordSetAt: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentAcceptRequest(BaseModel):
    """Request to accept an agent (empty body)"""
    pass


class AgentAcceptResponse(BaseModel):
    """Response after accepting an agent"""
    id: uuid.UUID
    status: AgentStatusEnum
    reviewedAt: datetime
    reviewedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentDeclineRequest(BaseModel):
    """Request to decline an agent"""
    reason: str = Field(..., min_length=1)


class AgentDeclineResponse(BaseModel):
    """Response after declining an agent"""
    id: uuid.UUID
    status: AgentStatusEnum
    declineReason: str
    reviewedAt: datetime
    reviewedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentStatusUpdateRequest(BaseModel):
    """Request to update an agent's status (admin-only)."""
    status: AgentStatusEnum
    reason: Optional[str] = None


class AgentStatusUpdateResponse(BaseModel):
    """Response after updating an agent's status."""
    id: uuid.UUID
    status: AgentStatusEnum
    statusReason: Optional[str] = None

    model_config = {"from_attributes": True}


class AgentDeleteResponse(BaseModel):
    """Response after soft deleting an agent"""
    id: uuid.UUID
    status: AgentStatusEnum
    deletedAt: datetime
    deletedBy: uuid.UUID

    model_config = {"from_attributes": True}


class PaginationInfo(BaseModel):
    """Pagination metadata"""
    page: int
    limit: int
    totalItems: int
    totalPages: int


class AgentListPaginatedResponse(BaseModel):
    """Paginated agent list response"""
    agents: List[AgentListResponse]
    pagination: PaginationInfo


# --- User Management (Admin) ---

class UserUpdate(BaseModel):
    """Partial update for user. All fields optional."""
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized


class RoleAssignmentRequest(BaseModel):
    """Request body for assigning a role to a user."""
    role_id: uuid.UUID


class PermissionsResponse(BaseModel):
    """List of permission codes for the current user."""
    permissions: List[str]

