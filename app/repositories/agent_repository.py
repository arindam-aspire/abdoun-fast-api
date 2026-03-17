"""
Repository for agent-related persistence: AgentInvite, AgentProfile, AdminAgentAssignment, and User+AgentProfile queries.
Encapsulates all DB access for the agents feature; no FastAPI or HTTP concerns.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import (
    AdminAgentAssignment,
    AgentInvite,
    AgentProfile,
    Role,
    User,
)


class AgentRepository:
    """Repository for agent invites, profiles, assignments, and user+profile lookups."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ---------- User + AgentProfile ----------

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (no eager loads)."""
        stmt = select(User).where(User.email == email)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_email_with_profile(self, email: str) -> Optional[User]:
        """Get user by email with profile loaded (for onboarding)."""
        stmt = (
            select(User)
            .where(User.email == email)
            .options(selectinload(User.profile))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_with_profile_and_roles(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by id with profile and roles loaded."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.profile), selectinload(User.roles))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_agent_with_profile(
        self, agent_id: uuid.UUID, include_deleted: bool = False
    ) -> Optional[Tuple[User, AgentProfile]]:
        """Get (User, AgentProfile) for an agent_id. By default excludes soft-deleted profiles."""
        stmt = (
            select(User, AgentProfile)
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(User.id == agent_id)
        )
        if not include_deleted:
            stmt = stmt.where(AgentProfile.deleted_at.is_(None))
        result = self._db.execute(stmt).first()
        return (result[0], result[1]) if result else None

    def list_agents_paginated(
        self,
        *,
        status: Optional[str],
        search: Optional[str],
        sort_by: str,
        sort_order: str,
        page: int,
        limit: int,
    ) -> Tuple[List[Tuple[User, AgentProfile]], int]:
        """
        List (User, AgentProfile) with filters and pagination.
        Returns (list of (user, profile), total_count).
        """
        base = (
            select(User, AgentProfile)
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(AgentProfile.deleted_at.is_(None))
        )
        base = self._apply_agent_filters(base, status, search)
        count_stmt = (
            select(func.count(User.id))
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(AgentProfile.deleted_at.is_(None))
        )
        count_stmt = self._apply_agent_filters(count_stmt, status, search)
        total = self._db.execute(count_stmt).scalar() or 0

        order_col = self._get_agent_order_column(sort_by)
        if sort_order.lower() == "asc":
            base = base.order_by(order_col.asc())
        else:
            base = base.order_by(order_col.desc())
        offset = (page - 1) * limit
        base = base.offset(offset).limit(limit)
        rows = self._db.execute(base).all()
        return [(r[0], r[1]) for r in rows], total

    def _apply_agent_filters(self, stmt, status: Optional[str], search: Optional[str]):
        if status:
            stmt = stmt.where(AgentProfile.status == status)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
        return stmt

    def _get_agent_order_column(self, sort_by: str):
        if sort_by == "invitedAt":
            return (
                AgentProfile.form_submitted_at
                if hasattr(AgentProfile, "form_submitted_at")
                else User.created_at
            )
        if sort_by == "email":
            return User.email
        if sort_by == "fullName":
            return User.full_name
        return User.created_at

    # ---------- AgentInvite ----------

    def find_unused_invite_by_email(
        self, email: str
    ) -> Optional[AgentInvite]:
        """Find an existing unused, non-revoked, non-expired invite for email."""
        stmt = select(AgentInvite).where(
            and_(
                AgentInvite.email == email,
                AgentInvite.is_used == False,
                AgentInvite.expires_at > datetime.now(),
                AgentInvite.revoked_at.is_(None),
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def add_invite(
        self,
        email: str,
        invited_by: uuid.UUID,
        token: str,
        expires_at: datetime,
        invited_at: datetime,
    ) -> AgentInvite:
        invite = AgentInvite(
            email=email,
            invited_by=invited_by,
            token=token,
            expires_at=expires_at,
            invited_at=invited_at,
        )
        self._db.add(invite)
        return invite

    def get_latest_invite_for_email(
        self, email: str
    ) -> Optional[Tuple[AgentInvite, Optional[str]]]:
        """Get latest invite for email and inviter full_name. Returns (invite, inviter_name)."""
        stmt = (
            select(AgentInvite, User.full_name)
            .outerjoin(User, User.id == AgentInvite.invited_by)
            .where(AgentInvite.email == email)
            .order_by(AgentInvite.created_at.desc())
        )
        row = self._db.execute(stmt).first()
        if not row:
            return None
        return (row[0], row[1])

    def get_latest_invite_by_email_only(self, email: str) -> Optional[AgentInvite]:
        """Get latest invite record by email (for resend/revoke)."""
        stmt = (
            select(AgentInvite)
            .where(AgentInvite.email == email)
            .order_by(AgentInvite.created_at.desc())
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def find_invite_by_token_valid(
        self, token: str
    ) -> Optional[AgentInvite]:
        """Find invite by token that is not expired and not revoked."""
        stmt = select(AgentInvite).where(
            and_(
                AgentInvite.token == token,
                AgentInvite.expires_at > datetime.now(),
                AgentInvite.revoked_at.is_(None),
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_invites_by_inviter(
        self, invited_by: uuid.UUID, used: Optional[bool] = None
    ) -> List[AgentInvite]:
        stmt = select(AgentInvite).where(AgentInvite.invited_by == invited_by)
        if used is not None:
            stmt = stmt.where(AgentInvite.is_used == used)
        stmt = stmt.order_by(AgentInvite.created_at.desc())
        return list(self._db.execute(stmt).scalars().all())

    def get_status_by_emails(self, emails: List[str]) -> dict:
        """Return mapping email -> AgentProfile.status for given emails."""
        if not emails:
            return {}
        stmt = (
            select(User.email, AgentProfile.status)
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(User.email.in_(emails))
        )
        rows = self._db.execute(stmt).all()
        return dict(rows)

    # ---------- User + AgentProfile creation/update ----------

    def get_role_by_name(self, name: str) -> Optional[Role]:
        stmt = select(Role).where(Role.name == name)
        return self._db.execute(stmt).scalar_one_or_none()

    def add_user(self, user: User) -> User:
        self._db.add(user)
        self._db.flush()
        return user

    def add_agent_profile(self, profile: AgentProfile) -> AgentProfile:
        self._db.add(profile)
        return profile

    def assign_role_to_user(self, user: User, role: Role) -> None:
        user.roles.append(role)

    # ---------- AdminAgentAssignment ----------

    def list_assignments(
        self,
        *,
        agent_id: Optional[uuid.UUID],
        admin_id: Optional[uuid.UUID],
    ) -> List[AdminAgentAssignment]:
        stmt = (
            select(AdminAgentAssignment)
            .options(
                selectinload(AdminAgentAssignment.admin),
                selectinload(AdminAgentAssignment.agent),
            )
        )
        conditions = []
        if agent_id is not None:
            conditions.append(AdminAgentAssignment.agent_id == agent_id)
        if admin_id is not None:
            conditions.append(AdminAgentAssignment.admin_id == admin_id)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(AdminAgentAssignment.assigned_at.desc())
        return list(self._db.execute(stmt).unique().scalars().all())

    def find_assignment(
        self, admin_id: uuid.UUID, agent_id: uuid.UUID
    ) -> Optional[AdminAgentAssignment]:
        stmt = select(AdminAgentAssignment).where(
            and_(
                AdminAgentAssignment.admin_id == admin_id,
                AdminAgentAssignment.agent_id == agent_id,
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def add_assignment(
        self,
        admin_id: uuid.UUID,
        agent_id: uuid.UUID,
        is_active: bool,
        can_inherit_privileges: bool,
    ) -> AdminAgentAssignment:
        assignment = AdminAgentAssignment(
            admin_id=admin_id,
            agent_id=agent_id,
            is_active=is_active,
            can_inherit_privileges=can_inherit_privileges,
        )
        self._db.add(assignment)
        return assignment

    # ---------- Transaction ----------

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, *instances: object) -> None:
        for obj in instances:
            self._db.refresh(obj)

    def flush(self, *instances: object) -> None:
        """Flush given instances to the DB (e.g. to get IDs before commit)."""
        for obj in instances:
            self._db.flush(obj)
