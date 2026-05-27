"""User, role, permission, agent profile, invite, and admin-agent assignment ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.models.recently_viewed_property import RecentlyViewedProperty
    from app.models.agency import Agency

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.property import Base
from app.utils.constants import AgentStatus

# Centralized FK target to avoid duplicated literals ("users.id")
FK_USERS_ID = "users.id"
ONDELETE_SET_NULL = "SET NULL"

# Association table for Many-to-Many relationship between Roles and Permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# Association table for Many-to-Many relationship between Users and Roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_by", UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now()),
)


class Permission(Base):
    """Permission code (e.g. user:create) that can be assigned to roles."""
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission(code='{self.code}')>"


class Role(Base):
    """Role (e.g. admin, agent) with many-to-many permissions and users."""
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    permissions: Mapped[List["Permission"]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )
    users: Mapped[List["User"]] = relationship(
        "User", 
        secondary=user_roles, 
        back_populates="roles",
        primaryjoin="Role.id == user_roles.c.role_id",
        secondaryjoin="User.id == user_roles.c.user_id"
    )

    def __repr__(self) -> str:
        return f"<Role(name='{self.name}')>"


class User(Base):
    """User account (Cognito-linked) with roles, optional agent profile, and assignments."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cognito_sub: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    agency_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agency_master.id", ondelete=ONDELETE_SET_NULL), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    profile_picture_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True
    )

    # Password-login brute-force protection (rolling window + temporary lockout).
    password_login_failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    password_login_first_failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_login_locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    roles: Mapped[List["Role"]] = relationship(
        "Role", 
        secondary=user_roles, 
        back_populates="users",
        primaryjoin="User.id == user_roles.c.user_id",
        secondaryjoin="Role.id == user_roles.c.role_id"
    )
    profile: Mapped[Optional["AgentProfile"]] = relationship(
        "AgentProfile", 
        back_populates="user", 
        uselist=False,
        foreign_keys="[AgentProfile.user_id]"
    )
    agency: Mapped[Optional["Agency"]] = relationship("Agency", back_populates="users")
    
    # Assignments where this user is the admin
    assigned_agents: Mapped[List["AdminAgentAssignment"]] = relationship(
        "AdminAgentAssignment", foreign_keys="AdminAgentAssignment.admin_id", back_populates="admin"
    )
    
    # Assignments where this user is the agent
    assigned_admins: Mapped[List["AdminAgentAssignment"]] = relationship(
        "AdminAgentAssignment", foreign_keys="AdminAgentAssignment.agent_id", back_populates="agent"
    )
    recent_views: Mapped[List[RecentlyViewedProperty]] = relationship(
        "RecentlyViewedProperty",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(email='{self.email}', full_name='{self.full_name}')>"


class AgentProfile(Base):
    """Agent-specific profile: service area, approval state, status, decline/review metadata."""
    __tablename__ = "agent_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), primary_key=True
    )
    service_area: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    form_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_set_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decline_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.INVITED, index=True)
    user: Mapped["User"] = relationship("User", back_populates="profile", foreign_keys=[user_id])
    approved_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])
    reviewed_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])
    deleted_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[deleted_by])


class AgentInvite(Base):
    """Invitation record for agent signup (token, expiry, used/revoked)."""
    __tablename__ = "agent_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True
    )

    inviter: Mapped["User"] = relationship("User", foreign_keys=[invited_by])
    revoker: Mapped[Optional["User"]] = relationship("User", foreign_keys=[revoked_by])


class AdminAgentAssignment(Base):
    """Assignment of an agent to an admin for privilege inheritance."""
    __tablename__ = "admin_agent_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_inherit_privileges: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    admin: Mapped["User"] = relationship("User", foreign_keys=[admin_id], back_populates="assigned_agents")
    agent: Mapped["User"] = relationship("User", foreign_keys=[agent_id], back_populates="assigned_admins")
