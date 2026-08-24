from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, false, func, or_, select
from sqlalchemy.orm import Session

from app.models.deal_closure import PropertyDealClosure
from app.models.live_schema import (
    ActivityLog,
    AgencyMaster,
    AgentProfile,
    Lead,
    PropertyListingSubmission,
    Role,
    User,
    UserRole,
)
from app.services.user_agencies import REL_AGENT, agency_user_ids


ADMIN_ROLE_NAMES = ("admin", "agency", "agency_admin")
ALL_ADMIN_ROLE_NAMES = ("admin", "agency", "agency_admin", "super_admin")
AGENT_ROLE_NAME = "agent"
ACTIVE_AGENT_STATUS = "ACTIVE"
PENDING_AGENT_STATUS = "PENDING_REVIEW"
PENDING_AGENCY_STATUS = "PENDING_APPROVAL"


@dataclass(frozen=True)
class DashboardScope:
    kind: str
    user_id: UUID
    agency_id: UUID | None = None


def _agency_user_ids(db: Session, agency_id: UUID):
    mapped_ids = agency_user_ids(db, agency_id=agency_id)
    return select(User.id).where(
        or_(
            User.id.in_(mapped_ids),
            User.agency_id == agency_id,
        )
    )


def _user_scope_condition(db: Session, scope: DashboardScope):
    if scope.kind == "super_admin":
        return None
    if scope.kind == "agency_admin":
        if scope.agency_id is None:
            return false()
        return User.id.in_(_agency_user_ids(db, scope.agency_id))
    return User.id == scope.user_id


def _listing_scope_condition(db: Session, scope: DashboardScope):
    if scope.kind == "super_admin":
        return None
    if scope.kind == "agency_admin":
        if scope.agency_id is None:
            return false()
        agency_users = _agency_user_ids(db, scope.agency_id)
        return or_(
            PropertyListingSubmission.agency_id == scope.agency_id,
            PropertyListingSubmission.agency_id.is_(None)
            & PropertyListingSubmission.submitted_by.in_(agency_users),
        )
    assigned_agent = PropertyListingSubmission.payload["_workflow"]["assigned_agent_id"].astext
    return or_(
        PropertyListingSubmission.submitted_by == scope.user_id,
        assigned_agent == str(scope.user_id),
    )


def _agency_property_ids(db: Session, scope: DashboardScope):
    condition = _listing_scope_condition(db, scope)
    stmt = select(PropertyListingSubmission.property_id).where(
        PropertyListingSubmission.deleted_at.is_(None),
        PropertyListingSubmission.property_id.is_not(None),
    )
    return stmt.where(condition) if condition is not None else stmt


def _lead_scope_condition(db: Session, scope: DashboardScope):
    if scope.kind == "super_admin":
        return None
    if scope.kind == "agency_admin":
        if scope.agency_id is None:
            return false()
        agency_users = _agency_user_ids(db, scope.agency_id)
        return or_(
            Lead.assigned_agent_id.in_(agency_users),
            Lead.created_by_agent_id.in_(agency_users),
            Lead.created_by_admin_id.in_(agency_users),
            Lead.property_id.in_(_agency_property_ids(db, scope)),
        )
    return or_(
        Lead.assigned_agent_id == scope.user_id,
        Lead.created_by_agent_id == scope.user_id,
    )


def get_user_counts(
    db: Session,
    *,
    scope: DashboardScope,
    current_start: datetime,
    next_start: datetime,
    previous_start: datetime,
    today_start: datetime,
    tomorrow_start: datetime,
) -> dict[str, int]:
    user_scope = _user_scope_condition(db, scope)
    conditions = [User.deleted_at.is_(None)]
    if user_scope is not None:
        conditions.append(user_scope)

    is_agent = Role.name == AGENT_ROLE_NAME
    is_admin = Role.name.in_(ADMIN_ROLE_NAMES)
    active_agent = is_agent & User.is_active.is_(True) & (AgentProfile.status == ACTIVE_AGENT_STATUS)
    pending_agent = (AgentProfile.status == PENDING_AGENT_STATUS) & AgentProfile.deleted_at.is_(None)
    stmt = (
        select(
            func.count(func.distinct(User.id)).label("total_users"),
            func.count(func.distinct(case((active_agent, User.id)))).label("total_agents"),
            func.count(func.distinct(case((is_admin, User.id)))).label("total_admins"),
            func.count(
                func.distinct(
                    case(
                        (
                            (User.created_at >= current_start)
                            & (User.created_at < next_start),
                            User.id,
                        )
                    )
                )
            ).label("users_current"),
            func.count(
                func.distinct(
                    case(
                        (
                            (User.created_at >= previous_start)
                            & (User.created_at < current_start),
                            User.id,
                        )
                    )
                )
            ).label("users_previous"),
            func.count(
                func.distinct(
                    case(
                        (
                            is_agent
                            & (User.created_at >= current_start)
                            & (User.created_at < next_start),
                            User.id,
                        )
                    )
                )
            ).label("agents_current"),
            func.count(
                func.distinct(
                    case(
                        (
                            is_agent
                            & (User.created_at >= previous_start)
                            & (User.created_at < current_start),
                            User.id,
                        )
                    )
                )
            ).label("agents_previous"),
            func.count(func.distinct(case((pending_agent, User.id)))).label(
                "pending_agents"
            ),
            func.count(
                func.distinct(
                    case(
                        (
                            pending_agent
                            & (AgentProfile.form_submitted_at >= today_start)
                            & (AgentProfile.form_submitted_at < tomorrow_start),
                            User.id,
                        )
                    )
                )
            ).label("pending_agents_today"),
        )
        .select_from(User)
        .outerjoin(UserRole, UserRole.user_id == User.id)
        .outerjoin(Role, Role.id == UserRole.role_id)
        .outerjoin(AgentProfile, AgentProfile.user_id == User.id)
        .where(*conditions)
    )
    row = db.execute(stmt).one()._mapping
    return {key: int(row[key] or 0) for key in row.keys()}


def get_user_growth(
    db: Session,
    *,
    scope: DashboardScope,
    start: datetime,
    end: datetime,
) -> list[tuple[Any, int]]:
    conditions = [
        User.deleted_at.is_(None),
        User.created_at >= start,
        User.created_at < end,
    ]
    user_scope = _user_scope_condition(db, scope)
    if user_scope is not None:
        conditions.append(user_scope)
    month = func.date_trunc("month", User.created_at).label("month")
    return [
        (row.month, int(row.count))
        for row in db.execute(
            select(month, func.count(User.id).label("count"))
            .where(*conditions)
            .group_by(month)
            .order_by(month)
        )
    ]


def get_listing_counts(
    db: Session,
    *,
    scope: DashboardScope,
    current_start: datetime,
    next_start: datetime,
    previous_start: datetime,
    today_start: datetime,
    tomorrow_start: datetime,
    pending_status: str,
) -> dict[str, int]:
    conditions = [PropertyListingSubmission.deleted_at.is_(None)]
    scope_condition = _listing_scope_condition(db, scope)
    if scope_condition is not None:
        conditions.append(scope_condition)
    pending = PropertyListingSubmission.status == pending_status
    row = db.execute(
        select(
            func.count(
                case(
                    (
                        (PropertyListingSubmission.created_at >= current_start)
                        & (PropertyListingSubmission.created_at < next_start),
                        1,
                    )
                )
            ).label("current"),
            func.count(
                case(
                    (
                        (PropertyListingSubmission.created_at >= previous_start)
                        & (PropertyListingSubmission.created_at < current_start),
                        1,
                    )
                )
            ).label("previous"),
            func.count(case((pending, 1))).label("pending"),
            func.count(
                case(
                    (
                        pending
                        & (PropertyListingSubmission.updated_at >= today_start)
                        & (PropertyListingSubmission.updated_at < tomorrow_start),
                        1,
                    )
                )
            ).label("pending_today"),
        ).where(*conditions)
    ).one()._mapping
    return {key: int(row[key] or 0) for key in row.keys()}


def get_listing_growth(
    db: Session,
    *,
    scope: DashboardScope,
    start: datetime,
    end: datetime,
) -> list[tuple[Any, int]]:
    conditions = [
        PropertyListingSubmission.deleted_at.is_(None),
        PropertyListingSubmission.created_at >= start,
        PropertyListingSubmission.created_at < end,
    ]
    scope_condition = _listing_scope_condition(db, scope)
    if scope_condition is not None:
        conditions.append(scope_condition)
    month = func.date_trunc("month", PropertyListingSubmission.created_at).label(
        "month"
    )
    return [
        (row.month, int(row.count))
        for row in db.execute(
            select(month, func.count(PropertyListingSubmission.id).label("count"))
            .where(*conditions)
            .group_by(month)
            .order_by(month)
        )
    ]


def get_lead_counts(
    db: Session,
    *,
    scope: DashboardScope,
    current_start: datetime,
    next_start: datetime,
    previous_start: datetime,
) -> dict[str, int]:
    conditions = []
    scope_condition = _lead_scope_condition(db, scope)
    if scope_condition is not None:
        conditions.append(scope_condition)
    row = db.execute(
        select(
            func.count(
                case(
                    (
                        (Lead.created_at >= current_start)
                        & (Lead.created_at < next_start),
                        1,
                    )
                )
            ).label("current"),
            func.count(
                case(
                    (
                        (Lead.created_at >= previous_start)
                        & (Lead.created_at < current_start),
                        1,
                    )
                )
            ).label("previous"),
        ).where(*conditions)
    ).one()._mapping
    return {key: int(row[key] or 0) for key in row.keys()}


def get_lead_growth(
    db: Session,
    *,
    scope: DashboardScope,
    start: datetime,
    end: datetime,
) -> list[tuple[Any, int]]:
    conditions = [Lead.created_at >= start, Lead.created_at < end]
    scope_condition = _lead_scope_condition(db, scope)
    if scope_condition is not None:
        conditions.append(scope_condition)
    month = func.date_trunc("month", Lead.created_at).label("month")
    return [
        (row.month, int(row.count))
        for row in db.execute(
            select(month, func.count(Lead.id).label("count"))
            .where(*conditions)
            .group_by(month)
            .order_by(month)
        )
    ]


def get_lead_sources(
    db: Session,
    *,
    scope: DashboardScope,
) -> list[tuple[str, int]]:
    conditions = []
    scope_condition = _lead_scope_condition(db, scope)
    if scope_condition is not None:
        conditions.append(scope_condition)
    return [
        (str(row.source), int(row.count))
        for row in db.execute(
            select(Lead.source, func.count(Lead.id).label("count"))
            .where(*conditions)
            .group_by(Lead.source)
            .order_by(Lead.source)
        )
    ]


def get_closed_deals_count(
    db: Session,
    *,
    scope: DashboardScope,
    current_start: datetime,
    next_start: datetime,
) -> int:
    conditions = [
        PropertyDealClosure.status == "APPROVED",
        PropertyDealClosure.reviewed_at >= current_start,
        PropertyDealClosure.reviewed_at < next_start,
    ]
    if scope.kind == "agency_admin":
        conditions.append(PropertyDealClosure.agency_id == scope.agency_id)
    elif scope.kind == "agent":
        conditions.append(PropertyDealClosure.requested_by == scope.user_id)
    return int(
        db.execute(
            select(func.count(PropertyDealClosure.id)).where(*conditions)
        ).scalar()
        or 0
    )


def get_pending_agency_counts(
    db: Session,
    *,
    today_start: datetime,
    tomorrow_start: datetime,
) -> tuple[int, int]:
    pending = AgencyMaster.status == PENDING_AGENCY_STATUS
    row = db.execute(
        select(
            func.count(case((pending, 1))).label("pending"),
            func.count(
                case(
                    (
                        pending
                        & (AgencyMaster.created_at >= today_start)
                        & (AgencyMaster.created_at < tomorrow_start),
                        1,
                    )
                )
            ).label("pending_today"),
        )
    ).one()
    return int(row.pending or 0), int(row.pending_today or 0)


def get_recent_activity(
    db: Session,
    *,
    scope: DashboardScope,
    limit: int = 10,
) -> list[ActivityLog]:
    stmt = select(ActivityLog).order_by(ActivityLog.created_at.desc())
    if scope.kind == "agency_admin":
        if scope.agency_id is None:
            return []
        agency_users = _agency_user_ids(db, scope.agency_id)
        stmt = stmt.where(
            or_(
                ActivityLog.user_id.in_(agency_users),
                ActivityLog.property_id.in_(_agency_property_ids(db, scope)),
            )
        )
    elif scope.kind == "agent":
        stmt = stmt.where(ActivityLog.user_id == scope.user_id)
    return db.execute(stmt.limit(limit)).scalars().all()


def get_health_context(
    db: Session,
    *,
    scope: DashboardScope,
) -> tuple[User | None, AgentProfile | None, AgencyMaster | None]:
    user = db.get(User, scope.user_id)
    profile = db.get(AgentProfile, scope.user_id) if scope.kind == "agent" else None
    agency = (
        db.get(AgencyMaster, scope.agency_id)
        if scope.kind == "agency_admin" and scope.agency_id
        else None
    )
    return user, profile, agency
