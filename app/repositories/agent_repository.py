"""Repository for agent invites, profiles, assignments, and user+profile persistence; no FastAPI/HTTP."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.models.user import (
    AdminAgentAssignment,
    AgentInvite,
    AgentProfile,
    Role,
    User,
)
from app.utils.constants import AgentSortField, SortOrder


class AgentRepository:
    """Repository for agent invites, profiles, assignments, and user+profile lookups."""

    def __init__(self, db: Session) -> None:
        """Store the database session for all operations.

        Args:
            db: SQLAlchemy Session (request-scoped).
        """
        self._db = db

    # ---------- User + AgentProfile ----------

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (no eager loads)."""
        stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_email_with_profile(self, email: str) -> Optional[User]:
        """Get user by email with profile loaded (for onboarding)."""
        stmt = (
            select(User)
            .where(User.email == email, User.deleted_at.is_(None))
            .options(selectinload(User.profile))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_with_profile_and_roles(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by id with profile and roles loaded."""
        stmt = (
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
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
            .where(User.id == agent_id, User.deleted_at.is_(None))
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
        """List (User, AgentProfile) with filters and pagination.

        Returns:
            Tuple of (list of (user, profile), total_count).
        """
        base = (
            select(User, AgentProfile)
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(User.deleted_at.is_(None), AgentProfile.deleted_at.is_(None))
        )
        base = self._apply_agent_filters(base, status, search)
        count_stmt = (
            select(func.count(User.id))
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(User.deleted_at.is_(None), AgentProfile.deleted_at.is_(None))
        )
        count_stmt = self._apply_agent_filters(count_stmt, status, search)
        total = self._db.execute(count_stmt).scalar() or 0

        order_col = self._get_agent_order_column(sort_by)
        if sort_order.lower() == SortOrder.ASC:
            base = base.order_by(order_col.asc())
        else:
            base = base.order_by(order_col.desc())
        offset = (page - 1) * limit
        base = base.offset(offset).limit(limit)
        rows = self._db.execute(base).all()
        return [(r[0], r[1]) for r in rows], total

    def list_all_agents_with_profiles(self) -> List[Tuple[User, AgentProfile]]:
        """Return all non-deleted agents as (User, AgentProfile), ordered by full name."""
        stmt = (
            select(User, AgentProfile)
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(User.deleted_at.is_(None), AgentProfile.deleted_at.is_(None))
            .order_by(User.full_name.asc())
        )
        rows = self._db.execute(stmt).all()
        return [(r[0], r[1]) for r in rows]

    def list_assignments_for_agents(self, agent_ids: List[uuid.UUID]) -> List[AdminAgentAssignment]:
        """All admin–agent assignments for the given agent ids (batch; avoids per-agent queries)."""
        if not agent_ids:
            return []
        stmt = (
            select(AdminAgentAssignment)
            .where(AdminAgentAssignment.agent_id.in_(agent_ids))
            .order_by(AdminAgentAssignment.agent_id, AdminAgentAssignment.assigned_at.desc())
        )
        return list(self._db.execute(stmt).unique().scalars().all())

    def get_latest_invites_for_emails(self, emails: List[str]) -> Dict[str, AgentInvite]:
        """Latest AgentInvite row per email (by created_at desc)."""
        if not emails:
            return {}
        stmt = (
            select(AgentInvite)
            .where(AgentInvite.email.in_(emails))
            .order_by(AgentInvite.email, AgentInvite.created_at.desc())
        )
        rows = list(self._db.execute(stmt).scalars().all())
        latest: Dict[str, AgentInvite] = {}
        for inv in rows:
            if inv.email not in latest:
                latest[inv.email] = inv
        return latest

    def _apply_agent_filters(self, stmt, status: Optional[str], search: Optional[str]):
        """Apply status and search (name/email) filters to the given statement."""
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
        """Resolve sort_by API name to SQLAlchemy column for ordering."""
        if sort_by == AgentSortField.INVITED_AT:
            return (
                AgentProfile.form_submitted_at
                if hasattr(AgentProfile, "form_submitted_at")
                else User.created_at
            )
        if sort_by == AgentSortField.EMAIL:
            return User.email
        if sort_by == AgentSortField.FULL_NAME:
            return User.full_name
        return User.created_at

    # ---------- AgentInvite ----------

    def find_unused_invite_by_email(
        self, email: str
    ) -> Optional[AgentInvite]:
        """Find an existing unused, non-revoked, non-expired invite for email."""
        now = datetime.now()
        stmt = select(AgentInvite).where(
            and_(
                AgentInvite.email == email,
                AgentInvite.is_used.is_(False),
                AgentInvite.expires_at > now,
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
        now = datetime.now()
        stmt = select(AgentInvite).where(
            and_(
                AgentInvite.token == token,
                AgentInvite.expires_at > now,
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
            .where(User.email.in_(emails), User.deleted_at.is_(None))
        )
        rows = self._db.execute(stmt).all()
        return dict(rows)

    # ---------- User + AgentProfile creation/update ----------

    def get_role_by_name(self, name: str) -> Optional[Role]:
        """Look up role by name (e.g. admin, agent)."""
        stmt = select(Role).where(Role.name == name)
        return self._db.execute(stmt).scalar_one_or_none()

    def add_user(self, user: User) -> User:
        """Persist user and flush to obtain ID."""
        self._db.add(user)
        self._db.flush()
        return user

    def add_agent_profile(self, profile: AgentProfile) -> AgentProfile:
        """Persist agent profile."""
        self._db.add(profile)
        return profile

    def assign_role_to_user(self, user: User, role: Role) -> None:
        """Append role to user's roles (many-to-many)."""
        user.roles.append(role)

    # ---------- AdminAgentAssignment ----------

    def list_assignments(
        self,
        *,
        agent_id: Optional[uuid.UUID],
        admin_id: Optional[uuid.UUID],
    ) -> List[AdminAgentAssignment]:
        """List admin-agent assignments with optional filters; includes admin and agent."""
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
        """Find active assignment for (admin_id, agent_id)."""
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

    def fetch_top_agents_leaderboard_window(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Agents with deals closed or inquiries in ``[period_start, period_end]`` inclusive (UTC).

        Returns rows: full_name, service_area, closed_deals, total_inquiries, responded_inquiries.

        Sort: (1) ``closed_deals`` descending — primary; (2) inquiry response rate descending — secondary;
        (3) ``full_name`` ascending.

        Inquiries: lead ``created_at`` in window; ``responded`` = ``updated_at > created_at``.
        """
        stmt = text(
            """
            WITH agent_scope AS (
                SELECT u.id AS user_id, u.full_name, ap.service_area
                FROM users u
                INNER JOIN agent_profiles ap ON ap.user_id = u.id AND ap.deleted_at IS NULL
            ),
            deals AS (
                SELECT p.agent_user_id AS user_id, COUNT(*)::int AS closed_deals
                FROM properties_normalized p
                WHERE COALESCE(p.deal_closed, false) = true
                  AND p.agent_user_id IS NOT NULL
                  AND p.updated_at >= :period_start
                  AND p.updated_at <= :period_end
                GROUP BY p.agent_user_id
            ),
            inquiries AS (
                SELECT
                    p.agent_user_id AS user_id,
                    COUNT(l.id)::int AS total_inquiries,
                    COUNT(l.id) FILTER (WHERE l.updated_at > l.created_at)::int AS responded_inquiries
                FROM leads l
                INNER JOIN properties_normalized p ON p.id = l.property_id
                WHERE p.agent_user_id IS NOT NULL
                  AND l.created_at >= :period_start
                  AND l.created_at <= :period_end
                GROUP BY p.agent_user_id
            )
            SELECT
                a.full_name,
                a.service_area,
                COALESCE(d.closed_deals, 0)::int AS closed_deals,
                COALESCE(i.total_inquiries, 0)::int AS total_inquiries,
                COALESCE(i.responded_inquiries, 0)::int AS responded_inquiries
            FROM agent_scope a
            LEFT JOIN deals d ON d.user_id = a.user_id
            LEFT JOIN inquiries i ON i.user_id = a.user_id
            WHERE COALESCE(d.closed_deals, 0) > 0 OR COALESCE(i.total_inquiries, 0) > 0
            ORDER BY
                COALESCE(d.closed_deals, 0) DESC,
                CASE
                    WHEN COALESCE(i.total_inquiries, 0) > 0
                    THEN COALESCE(i.responded_inquiries, 0)::float / NULLIF(i.total_inquiries, 0)
                    ELSE 0.0
                END DESC,
                a.full_name ASC
            LIMIT :limit
            """
        )
        rows = self._db.execute(
            stmt,
            {
                "period_start": period_start,
                "period_end": period_end,
                "limit": limit,
            },
        ).mappings().all()
        return [dict(r) for r in rows]

    # ---------- Transaction ----------

    def commit(self) -> None:
        """Commit the current transaction."""
        self._db.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._db.rollback()

    def refresh(self, *instances: object) -> None:
        """Refresh given instances from the DB."""
        for obj in instances:
            self._db.refresh(obj)

    def flush(self, *instances: object) -> None:
        """Flush given instances to the DB (e.g. to get IDs before commit)."""
        for obj in instances:
            self._db.flush(obj)
