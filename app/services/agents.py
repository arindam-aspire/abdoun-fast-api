from __future__ import annotations

import math
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.live_schema import AgentInvite, AgentProfile, User
from app.services.auth import assign_role, normalize_username, utc_now
from app.services.notifications import send_email_notification
from app.services.user_agencies import REL_AGENT, agency_user_ids, ensure_user_agency_mapping, user_has_active_agency_mapping
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_FORBIDDEN, STATUS_NOT_FOUND


AGENT_STATUSES = {"ACTIVE", "INVITED", "PENDING_REVIEW", "DECLINED", "INACTIVE", "DELETED"}


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def serialize_agent(user: User, profile: AgentProfile | None, invited_by: str | None = None, invited_at=None) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "fullName": user.full_name,
        "phone": user.phone_number or "",
        "serviceArea": profile.service_area if profile else "",
        "status": (profile.status if profile else "INVITED") or "INVITED",
        "invitedAt": _iso(invited_at),
        "invitedBy": invited_by,
        "formSubmittedAt": _iso(profile.form_submitted_at) if profile else None,
        "reviewedAt": _iso(profile.reviewed_at) if profile else None,
        "declineReason": profile.decline_reason if profile else None,
    }


def list_agents(
    db: Session,
    *,
    agency_id: UUID | None,
    roles: tuple[str, ...],
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size
    is_super_admin = "super_admin" in {role.lower() for role in roles}
    if not is_super_admin and agency_id is None:
        return {
            "agents": [],
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": 0,
                "totalPages": 1,
                "hasNext": False,
                "hasPrevious": False,
            },
        }

    stmt = (
        select(User, AgentProfile, AgentInvite)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .outerjoin(AgentInvite, AgentInvite.email == User.email)
        .where(AgentProfile.deleted_at.is_(None))
    )

    if not is_super_admin and agency_id:
        mapped_user_ids = agency_user_ids(db, agency_id=agency_id, relationship_types=(REL_AGENT,))
        stmt = stmt.where(or_(User.id.in_(mapped_user_ids), User.agency_id == agency_id))

    sort_columns = {
        "invited_at": AgentInvite.invited_at,
        "email": User.email,
        "fullName": User.full_name,
        "status": AgentProfile.status,
        "reviewedAt": AgentProfile.reviewed_at,
        "formSubmittedAt": AgentProfile.form_submitted_at,
    }
    sort_column = sort_columns.get(sort_by, AgentInvite.invited_at)
    stmt = stmt.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc().nullslast())

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(stmt.offset(offset).limit(page_size)).all()
    agents = [
        serialize_agent(
            user,
            profile,
            invited_by=str(invite.invited_by) if invite else None,
            invited_at=invite.invited_at if invite else None,
        )
        for user, profile, invite in rows
    ]

    total_pages = math.ceil(total / page_size) if total else 1
    pagination = {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }
    return {"agents": agents, "pagination": pagination}


def invite_agent(
    db: Session,
    *,
    email: str,
    invited_by: UUID,
    agency_id: UUID | None,
    full_name: str | None = None,
    phone_number: str | None = None,
    service_area: str | None = None,
) -> dict:
    if agency_id is None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency Admin must belong to an agency")
    normalized_email = normalize_username(email)
    lookup_conditions = [User.email == normalized_email]
    if phone_number:
        lookup_conditions.append(User.phone_number == phone_number)
    user = db.execute(select(User).where(or_(*lookup_conditions))).scalar_one_or_none()

    if not user:
        user = User(
            id=uuid4(),
            full_name=full_name or normalized_email,
            email=normalized_email,
            phone_number=phone_number,
            is_active=True,
            is_email_verified=False,
            is_phone_verified=False,
            preferred_language="en",
            agency_id=agency_id,
        )
        db.add(user)
        db.flush()
    elif agency_id and not user.agency_id:
        user.agency_id = agency_id

    assign_role(db, user.id, "agent", assigned_by=invited_by)
    ensure_user_agency_mapping(
        db,
        user_id=user.id,
        agency_id=agency_id,
        relationship_type=REL_AGENT,
        actor_user_id=invited_by,
    )

    profile = db.get(AgentProfile, user.id)
    if not profile:
        profile = AgentProfile(
            user_id=user.id,
            service_area=service_area,
            status="INVITED",
        )
        db.add(profile)
    else:
        profile.service_area = service_area if service_area is not None else profile.service_area
        if profile.status == "DELETED":
            profile.status = "INVITED"
            profile.deleted_at = None

    token = secrets.token_urlsafe(32)
    invite = AgentInvite(
        id=uuid4(),
        email=normalized_email,
        invited_by=invited_by,
        token=token,
        expires_at=utc_now() + timedelta(days=7),
        is_used=False,
        invited_at=utc_now(),
    )
    db.add(invite)
    send_email_notification(
        to_email=normalized_email,
        subject="Abdoun agent invitation",
        body=f"You have been invited as an agent. Dev invite token: {token}",
    )
    db.flush()
    return serialize_agent(user, profile, invited_by=str(invited_by), invited_at=invite.invited_at)


def update_agent_status(
    db: Session,
    *,
    agent_id: UUID,
    actor_id: UUID,
    actor_agency_id: UUID | None,
    status: str,
    reason: str | None = None,
) -> dict:
    normalized_status = status.strip().upper()
    if normalized_status not in AGENT_STATUSES:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid agent status")

    user = db.get(User, agent_id)
    profile = db.get(AgentProfile, agent_id)
    if not user or not profile:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agent not found")
    has_mapping = bool(
        actor_agency_id
        and user_has_active_agency_mapping(
            db,
            user_id=user.id,
            agency_id=actor_agency_id,
            relationship_type=REL_AGENT,
        )
    )
    has_legacy_agency = bool(actor_agency_id and user.agency_id == actor_agency_id)
    if actor_agency_id is None or not (has_mapping or has_legacy_agency):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent is outside the agency")

    profile.status = normalized_status
    profile.reviewed_by = actor_id
    profile.reviewed_at = utc_now()
    profile.status_reason = reason
    if normalized_status == "ACTIVE":
        profile.approved_by = actor_id
        profile.approved_at = utc_now()
        profile.decline_reason = None
    elif normalized_status == "DECLINED":
        profile.decline_reason = reason
    return serialize_agent(user, profile)
