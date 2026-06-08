"""Pydantic schemas for auth, user, role, permission, and agent API request/response."""
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, EmailStr, Field, computed_field, field_validator

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
    role: Optional[str] = Field(
        default=None,
        description="Optional role for registration (e.g. AGENCY_ADMIN/admin).",
    )

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


class AccountUserStatus(str, Enum):
    """Derived lifecycle status from deleted_at + is_active (API-facing; raw audit fields excluded)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DELETED = "DELETED"


class UserAgencyResponse(BaseModel):
    agency_id: uuid.UUID = Field(
        ...,
        validation_alias=AliasChoices("agency_id", "id"),
    )
    agency_name: Optional[str] = None
    agency_trade_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    currency: Optional[str] = None
    measurement_unit: Optional[str] = None

    model_config = {"from_attributes": True}


class UserResponse(UserBase):
    """User profile response with roles and verification flags."""
    id: uuid.UUID
    is_active: bool
    is_email_verified: bool
    is_phone_verified: bool
    profile_picture_url: Optional[str] = None
    agency: Optional[UserAgencyResponse] = None
    roles: List[RoleResponse] = []
    created_at: datetime
    requires_password_set: bool = Field(False, description="True if user must set a password (e.g. agent who signed in via OTP and has not set one)")
    deleted_at: Optional[datetime] = Field(default=None, exclude=True)
    deleted_by: Optional[uuid.UUID] = Field(default=None, exclude=True)

    model_config = {"from_attributes": True}

    @computed_field
    def status(self) -> AccountUserStatus:
        if self.deleted_at is not None:
            return AccountUserStatus.DELETED
        if self.is_active:
            return AccountUserStatus.ACTIVE
        return AccountUserStatus.INACTIVE


class UserTypeQuery(str, Enum):
    """GET /users ``userType`` query; ``register_user`` maps to DB role ``registered_user``."""

    REGISTER_USER = "register_user"
    ADMIN = "admin"
    AGENT = "agent"


class UsersListPaginatedResponse(BaseModel):
    """Admin user list with pagination.

    ``pageSize``, ``totalPages``, ``hasNext``, ``hasPrevious`` are the canonical fields per policy.
    """

    users: List[UserResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool

    model_config = {"from_attributes": True}


class ProfilePictureUploadRequest(BaseModel):
    """Request to obtain a presigned PUT URL for the current user's profile picture (same shape as property image presigned step)."""

    file_name: str
    content_type: str
    file_size: int | None = None


class ProfilePictureUploadData(BaseModel):
    """Presigned upload targets plus the persisted public URL for the profile picture."""

    profile_picture_url: str
    upload_url: str
    expires_in: int

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int
    # In response body only (not in JWT). True = first-time agent without password; show set-password UI.
    requires_password_set: bool = Field(False, description="True if user must set a password (e.g. agent who signed in via OTP and has not set one)")
    remember_me_cookie: bool = Field(
        False,
        description="True when refresh is bound to an HttpOnly Remember Me cookie instead of the response body.",
    )

class LoginRequest(BaseModel):
    """Login request (username = email or phone, password)."""
    username: str = Field(
        ...,
        validation_alias=AliasChoices("username", "email"),
        description="Email or phone. 'email' is accepted as an alias for backward compatibility.",
    )
    password: str
    role: Optional[str] = Field(
        default=None,
        description="Optional role hint for login guard (e.g. AGENCY_ADMIN/admin).",
    )
    remember_me: bool = Field(
        default=False,
        validation_alias=AliasChoices("remember_me", "rememberMe"),
        description="If true, issue a long-lived Remember Me session (max 30 days) via HttpOnly cookie.",
    )

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

    refresh_token: Optional[str] = None
    # Required when Cognito app client has a secret (for SECRET_HASH). Use sub or email from login/id_token.
    username: Optional[str] = None

    @field_validator("refresh_token", mode="before")
    @classmethod
    def refresh_token_empty_as_none(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

class OTPVerify(BaseModel):
    """Verify OTP (username, code, session from /login/otp/request)."""
    username: str  # email or phone (E.164); same as in /login/otp/request
    code: str
    session: str
    remember_me: bool = Field(
        default=False,
        validation_alias=AliasChoices("remember_me", "rememberMe"),
        description="If true, issue a long-lived Remember Me session (max 30 days) via HttpOnly cookie.",
    )

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
    """Pagination metadata (canonical format)."""

    page: int
    pageSize: int
    total: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool


class AgentListPaginatedResponse(BaseModel):
    """Paginated agent list response"""
    agents: List[AgentListResponse]
    pagination: PaginationInfo


class AgentSummaryAssignmentItem(BaseModel):
    """One admin–agent assignment: DB fields plus assignmentStatus (see AgentAssignmentStatus)."""

    id: uuid.UUID
    adminId: uuid.UUID
    isActive: bool
    revokedAt: Optional[datetime] = None
    canInheritPrivileges: bool
    assignedAt: datetime
    assignmentStatus: str

    model_config = {"from_attributes": True}


class AgentSummaryLatestInvite(BaseModel):
    """Latest agent_invites row for the user email (by created_at), as stored."""

    isUsed: bool
    revokedAt: Optional[datetime] = None
    expiresAt: datetime
    invitedAt: Optional[datetime] = None
    createdAt: datetime

    model_config = {"from_attributes": True}


class AgentSummaryMetadata(BaseModel):
    """Profile and user fields that sit alongside status (raw values from ORM)."""

    email: str
    userCreatedAt: datetime
    cognitoSub: Optional[str] = None
    serviceArea: Optional[str] = None
    statusReason: Optional[str] = None
    declineReason: Optional[str] = None
    reviewedAt: Optional[datetime] = None
    reviewedBy: Optional[uuid.UUID] = None
    formSubmittedAt: Optional[datetime] = None
    passwordSetAt: Optional[datetime] = None
    approvedAt: Optional[datetime] = None
    approvedBy: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


class AgentSummaryItem(BaseModel):
    """One agent in GET /agents/summary: profileStatus and related state (no enum coercion on profileStatus)."""

    agentId: uuid.UUID
    agentName: str
    profileStatus: str
    userIsActive: bool
    assignments: List[AgentSummaryAssignmentItem]
    latestInvite: Optional[AgentSummaryLatestInvite] = None
    metadata: AgentSummaryMetadata

    model_config = {"from_attributes": True}


class AgentSummaryResponse(BaseModel):
    """Response for Admin: agent summary KPIs plus ``lastFiveAgents`` only (no full agent list)."""

    totalAgents: int
    activeAgents: int
    pendingInvites: int
    pendingReview: int
    declined: int
    lastFiveAgents: List[AgentSummaryItem]

    model_config = {"from_attributes": True}


class TopAgentLeaderboardItem(BaseModel):
    """One agent on the leaderboard: rank by closed deals first, inquiry response rate second."""

    name: str
    closedDeals: int
    responseRate: str
    area: Optional[str] = None

    model_config = {"from_attributes": True}


class TopAgentsLeaderboardResponse(BaseModel):
    """Leaderboard window: ``firstDate`` = 30 days before ``lastDate``; ``lastDate`` = request time (UTC)."""

    firstDate: datetime
    lastDate: datetime
    agents: List[TopAgentLeaderboardItem]

    model_config = {"from_attributes": True}


class DashboardRecentActivityItem(BaseModel):
    """Recent activity item displayed in dashboard timeline."""

    text: str
    time: str
    tone: str


class AgentPropertyPerformanceItem(BaseModel):
    """Property performance item on agent dashboard (same shape as admin dashboard item)."""

    label: str
    value: int = Field(ge=0)
    propertyId: str
    propertyTitle: str = ""
    propertyType: str = ""
    agentId: Optional[str] = None
    agentName: str


class AgentDashboardSummaryResponse(BaseModel):
    """Dashboard summary for currently authenticated admin/agent scope."""

    totalProperties: int
    leadsThisMonth: int
    dealCloseCount: int
    conversionRate: int
    totalPropertyViews: int
    activeProperties: int
    draftProperties: int
    inquiryVolumeAllTime: int
    inquiryVolumeLast7Days: int
    inquiryTrendLast30Days: List[int]
    listingsChangePercent: float
    leadsChangePercent: float
    dealsClosedChangePercent: float
    propertyViewsChangePercent: float
    propertyPerformance: List[AgentPropertyPerformanceItem] = Field(default_factory=list)
    recentActivity: List[DashboardRecentActivityItem]


# --- Self-service profile (authenticated; unified request / verify) ---


class ProfileUpdateRequest(BaseModel):
    """Optional fields; at least one must be present. Name applies immediately; email/phone need verify."""

    full_name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized


class ProfileUpdateRequestResponse(BaseModel):
    """Response from PATCH /auth/me/profile/request."""

    message: str
    requires_verification: bool
    verification_fields: List[str] = Field(default_factory=list)
    dev_phone_otp: Optional[str] = Field(
        default=None,
        description="Phone OTP for verify step until SMS is integrated; omitted if PROFILE_OTP_HIDE_PHONE_CODE_IN_RESPONSE=true.",
    )
    dev_email_otp: Optional[str] = Field(
        default=None,
        description="Email OTP returned in API for staging/agency when outbound email is unavailable.",
    )
    otp: Optional[str] = Field(
        default=None,
        description="Convenience copy of pending OTP (dev_email_otp if present, else dev_phone_otp).",
    )


class ProfileUpdateVerifyRequest(BaseModel):
    """Verify pending email and/or phone using OTPs from the request step."""

    email: Optional[EmailStr] = None
    email_otp: Optional[str] = Field(None, min_length=4, max_length=16)
    phone_number: Optional[str] = None
    phone_otp: Optional[str] = Field(None, min_length=4, max_length=16)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = _normalize_phone(v)
        if not re.match(PHONE_E164_REGEX, normalized):
            raise ValueError(ValidationMessages.PHONE_E164)
        return normalized


class ProfileUpdateVerifyResponse(BaseModel):
    """Response from POST /auth/me/profile/verify."""

    message: str


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

