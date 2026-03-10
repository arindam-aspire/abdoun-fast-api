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
    status: str  # "ACTIVE ✓" or "INACTIVE/REVOKED ✗"

    model_config = {"from_attributes": True}


# --- Agent Onboarding Schemas ---

class AgentInviteRequest(BaseModel):
    """Request to invite an agent (admin endpoint)"""
    email: EmailStr


class AgentInviteResponse(BaseModel):
    """Response after inviting an agent"""
    id: uuid.UUID
    email: str
    status: str
    inviteLink: str
    invitedAt: datetime
    invitedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentOnboardingFormRequest(BaseModel):
    """Request to submit agent onboarding form"""
    fullName: str = Field(..., min_length=1)
    phone: str
    serviceArea: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.PHONE_E164)
        return v


class AgentOnboardingFormResponse(BaseModel):
    """Response after submitting onboarding form"""
    email: str
    status: str
    formSubmittedAt: datetime

    model_config = {"from_attributes": True}


class AgentValidateInviteResponse(BaseModel):
    """Response when validating invite token"""
    email: str
    status: str
    alreadySubmitted: bool


class AgentListResponse(BaseModel):
    """Agent list item response"""
    id: uuid.UUID
    email: str
    fullName: Optional[str] = None
    phone: Optional[str] = None
    serviceArea: Optional[str] = None
    status: str
    invitedAt: Optional[datetime] = None
    invitedBy: Optional[uuid.UUID] = None
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
    status: str
    invitedAt: Optional[datetime] = None
    invitedBy: Optional[uuid.UUID] = None
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
    status: str
    reviewedAt: datetime
    reviewedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentDeclineRequest(BaseModel):
    """Request to decline an agent"""
    reason: str = Field(..., min_length=1)


class AgentDeclineResponse(BaseModel):
    """Response after declining an agent"""
    id: uuid.UUID
    status: str
    declineReason: str
    reviewedAt: datetime
    reviewedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentDeleteResponse(BaseModel):
    """Response after soft deleting an agent"""
    id: uuid.UUID
    status: str
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
        if v is not None and not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.PHONE_E164)
        return v


class RoleAssignmentRequest(BaseModel):
    """Request body for assigning a role to a user."""
    role_id: uuid.UUID


class PermissionsResponse(BaseModel):
    """List of permission codes for the current user."""
    permissions: List[str]


# --- Agent Onboarding Schemas (New API) ---

class AgentOnboardingFormRequest(BaseModel):
    """Request to submit agent onboarding form"""
    fullName: str = Field(..., min_length=1)
    phone: str
    serviceArea: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(PHONE_E164_REGEX, v):
            raise ValueError(ValidationMessages.PHONE_E164)
        return v


class AgentOnboardingFormResponse(BaseModel):
    """Response after submitting onboarding form"""
    email: str
    status: str
    formSubmittedAt: datetime

    model_config = {"from_attributes": True}


class AgentValidateInviteResponse(BaseModel):
    """Response when validating invite token"""
    email: str
    status: str
    alreadySubmitted: bool


class AgentListResponse(BaseModel):
    """Agent list item response"""
    id: uuid.UUID
    email: str
    fullName: Optional[str] = None
    phone: Optional[str] = None
    serviceArea: Optional[str] = None
    status: str
    invitedAt: Optional[datetime] = None
    invitedBy: Optional[uuid.UUID] = None
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
    status: str
    invitedAt: Optional[datetime] = None
    invitedBy: Optional[uuid.UUID] = None
    formSubmittedAt: Optional[datetime] = None
    reviewedAt: Optional[datetime] = None
    reviewedBy: Optional[uuid.UUID] = None
    declineReason: Optional[str] = None
    passwordSetAt: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentInviteResponse(BaseModel):
    """Response after inviting an agent"""
    id: uuid.UUID
    email: str
    status: str
    inviteLink: str
    invitedAt: datetime
    invitedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentAcceptRequest(BaseModel):
    """Request to accept an agent (empty body)"""
    pass


class AgentAcceptResponse(BaseModel):
    """Response after accepting an agent"""
    id: uuid.UUID
    status: str
    reviewedAt: datetime
    reviewedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentDeclineRequest(BaseModel):
    """Request to decline an agent"""
    reason: str = Field(..., min_length=1)


class AgentDeclineResponse(BaseModel):
    """Response after declining an agent"""
    id: uuid.UUID
    status: str
    declineReason: str
    reviewedAt: datetime
    reviewedBy: uuid.UUID

    model_config = {"from_attributes": True}


class AgentDeleteResponse(BaseModel):
    """Response after soft deleting an agent"""
    id: uuid.UUID
    status: str
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
