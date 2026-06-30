from __future__ import annotations

import math
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.live_schema import AgentInvite, AgentProfile, User
from app.services.auth import assign_role, mark_password_set, normalize_username, utc_now
from app.core.security import hash_secret
from app.services.notifications import send_email_notification
from app.services.user_agencies import REL_AGENT, agency_user_ids, ensure_user_agency_mapping, user_has_active_agency_mapping
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_FORBIDDEN, STATUS_NOT_FOUND


AGENT_STATUSES = {"ACTIVE", "INVITED", "PENDING_REVIEW", "DECLINED", "INACTIVE", "DELETED"}


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _invite_link(token: str) -> str:
    return f"/agent-invite?token={token}"


def _invite_expiry() -> timedelta:
    return timedelta(seconds=get_settings().agent_invitation_ttl_seconds)


def _is_expired(invite: AgentInvite) -> bool:
    current_time = utc_now()
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        current_time = current_time.replace(tzinfo=None)
    return expires_at < current_time


def _active_invite_for_email(db: Session, email: str) -> AgentInvite | None:
    return db.execute(
        select(AgentInvite)
        .where(
            AgentInvite.email == normalize_username(email),
            AgentInvite.revoked_at.is_(None),
            AgentInvite.is_used.is_(False),
        )
        .order_by(AgentInvite.invited_at.desc().nullslast(), AgentInvite.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _revoke_active_invites(db: Session, *, email: str, actor_id: UUID) -> None:
    invites = db.execute(
        select(AgentInvite).where(
            AgentInvite.email == normalize_username(email),
            AgentInvite.revoked_at.is_(None),
            AgentInvite.is_used.is_(False),
        )
    ).scalars().all()
    for invite in invites:
        invite.revoked_at = utc_now()
        invite.revoked_by = actor_id


def serialize_agent_invite(user: User, invite: AgentInvite) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "status": "INVITED",
        "inviteLink": _invite_link(invite.token),
        "invitedAt": _iso(invite.invited_at) or _iso(invite.created_at),
        "invitedBy": str(invite.invited_by),
    }


def serialize_agent_invitation_preview(user: User, invite: AgentInvite, profile: AgentProfile | None) -> dict:
    return {
        "id": str(invite.id),
        "email": invite.email,
        "fullName": user.full_name,
        "phone": user.phone_number or "",
        "serviceArea": profile.service_area if profile else "",
        "status": "EXPIRED" if _is_expired(invite) else (profile.status if profile else "INVITED"),
        "expiresAt": _iso(invite.expires_at),
    }


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
    search: str | None = None,
    status: str | None = None,
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
        select(User, AgentProfile)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .where(AgentProfile.deleted_at.is_(None))
    )

    if not is_super_admin and agency_id:
        mapped_user_ids = agency_user_ids(db, agency_id=agency_id, relationship_types=(REL_AGENT,))
        stmt = stmt.where(or_(User.id.in_(mapped_user_ids), User.agency_id == agency_id))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern), User.phone_number.ilike(pattern)))
    normalized_status = _normalize_status_filter(status)
    if normalized_status:
        stmt = stmt.where(AgentProfile.status == normalized_status)

    sort_columns = {
        "invited_at": User.created_at,
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
        for user, profile in rows
        for invite in [_active_invite_for_email(db, user.email)]
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


def _normalize_status_filter(status: str | None) -> str | None:
    value = (status or "").strip().lower()
    if not value or value == "all":
        return None
    mapping = {
        "active": "ACTIVE",
        "inactive": "INACTIVE",
        "invited": "INVITED",
        "pending": "PENDING_REVIEW",
        "pending_review": "PENDING_REVIEW",
        "declined": "DECLINED",
        "deleted": "DELETED",
    }
    return mapping.get(value, status.strip().upper())


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

    _revoke_active_invites(db, email=normalized_email, actor_id=invited_by)
    token = secrets.token_urlsafe(32)
    invite = AgentInvite(
        id=uuid4(),
        email=normalized_email,
        invited_by=invited_by,
        token=token,
        expires_at=utc_now() + _invite_expiry(),
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
    return serialize_agent_invite(user, invite)


def get_agent_invitation_by_token(db: Session, token: str) -> tuple[AgentInvite, User, AgentProfile | None]:
    invite = db.execute(select(AgentInvite).where(AgentInvite.token == token)).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Invitation not found")
    if invite.revoked_at is not None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invitation has been revoked")
    if invite.is_used:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invitation has already been used")
    if _is_expired(invite):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invitation link has expired")

    user = db.execute(select(User).where(User.email == invite.email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Invited agent account not found")
    profile = db.get(AgentProfile, user.id)
    return invite, user, profile


def validate_agent_invitation(db: Session, *, token: str) -> dict:
    invite, user, profile = get_agent_invitation_by_token(db, token)
    return serialize_agent_invitation_preview(user, invite, profile)


def accept_agent_invitation(db: Session, *, token: str, password: str) -> dict:
    invite, user, profile = get_agent_invitation_by_token(db, token)
    user.password_hash = hash_secret(password)
    user.is_active = True
    user.is_email_verified = True
    invite.is_used = True

    if not profile:
        profile = AgentProfile(user_id=user.id)
        db.add(profile)
    profile.status = "ACTIVE"
    profile.deleted_at = None
    profile.decline_reason = None
    profile.approved_by = invite.invited_by
    profile.approved_at = utc_now()
    profile.reviewed_by = invite.invited_by
    profile.reviewed_at = utc_now()
    profile.password_set_at = utc_now()
    mark_password_set(db, user)
    db.flush()
    return serialize_agent(user, profile, invited_by=str(invite.invited_by), invited_at=invite.invited_at)


def manual_onboard_agent(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone: str | None,
    service_area: str | None,
    actor_id: UUID,
    agency_id: UUID | None,
) -> dict:
    if agency_id is None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency Admin must belong to an agency")
    normalized_email = normalize_username(email)
    existing = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    temporary_password = secrets.token_urlsafe(10)
    if existing:
        user = existing
        if agency_id and not user.agency_id:
            user.agency_id = agency_id
        user.full_name = full_name or user.full_name
        user.phone_number = phone or user.phone_number
        user.is_active = True
        if not user.password_hash:
            user.password_hash = hash_secret(temporary_password)
    else:
        user = User(
            id=uuid4(),
            full_name=full_name,
            email=normalized_email,
            phone_number=phone,
            is_active=True,
            is_email_verified=True,
            is_phone_verified=False,
            preferred_language="en",
            agency_id=agency_id,
            password_hash=hash_secret(temporary_password),
        )
        db.add(user)
        db.flush()

    assign_role(db, user.id, "agent", assigned_by=actor_id)
    ensure_user_agency_mapping(
        db,
        user_id=user.id,
        agency_id=agency_id,
        relationship_type=REL_AGENT,
        actor_user_id=actor_id,
    )
    profile = db.get(AgentProfile, user.id)
    if not profile:
        profile = AgentProfile(user_id=user.id)
        db.add(profile)
    profile.service_area = service_area
    profile.status = "ACTIVE"
    profile.approved_by = actor_id
    profile.approved_at = utc_now()
    profile.reviewed_by = actor_id
    profile.reviewed_at = utc_now()
    profile.deleted_at = None
    profile.decline_reason = None
    _revoke_active_invites(db, email=normalized_email, actor_id=actor_id)
    db.flush()
    return {
        "id": str(user.id),
        "email": user.email,
        "fullName": user.full_name,
        "phone": user.phone_number or "",
        "serviceArea": profile.service_area or "",
        "status": profile.status,
        "temporaryPassword": temporary_password,
    }


def resend_agent_invitation(
    db: Session,
    *,
    agent_id: UUID,
    actor_id: UUID,
    agency_id: UUID | None,
) -> dict:
    if agency_id is None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency Admin must belong to an agency")
    user = db.get(User, agent_id)
    profile = db.get(AgentProfile, agent_id)
    if not user or not profile:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agent not found")
    if not _agent_in_agency(db, user=user, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent is outside the agency")
    _revoke_active_invites(db, email=user.email, actor_id=actor_id)
    token = secrets.token_urlsafe(32)
    invite = AgentInvite(
        id=uuid4(),
        email=user.email,
        invited_by=actor_id,
        token=token,
        expires_at=utc_now() + _invite_expiry(),
        is_used=False,
        invited_at=utc_now(),
    )
    db.add(invite)
    profile.status = "INVITED"
    send_email_notification(
        to_email=user.email,
        subject="Abdoun agent invitation",
        body=f"You have been invited as an agent. Dev invite token: {token}",
    )
    db.flush()
    return serialize_agent_invite(user, invite)


def _agent_in_agency(db: Session, *, user: User, agency_id: UUID) -> bool:
    return user_has_active_agency_mapping(
        db,
        user_id=user.id,
        agency_id=agency_id,
        relationship_type=REL_AGENT,
    ) or user.agency_id == agency_id


def delete_agent(
    db: Session,
    *,
    agent_id: UUID,
    actor_id: UUID,
    agency_id: UUID | None,
) -> None:
    if agency_id is None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency Admin must belong to an agency")
    user = db.get(User, agent_id)
    profile = db.get(AgentProfile, agent_id)
    if not user or not profile:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agent not found")
    if not _agent_in_agency(db, user=user, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent is outside the agency")
    profile.status = "DELETED"
    profile.deleted_at = utc_now()
    profile.deleted_by = actor_id
    user.is_active = False
    _revoke_active_invites(db, email=user.email, actor_id=actor_id)


def agent_summary(
    db: Session,
    *,
    agency_id: UUID | None,
    roles: tuple[str, ...],
) -> dict:
    data = list_agents(
        db,
        agency_id=agency_id,
        roles=roles,
        page=1,
        page_size=1000,
        sort_by="invited_at",
        sort_order="desc",
        search=None,
        status=None,
    )
    agents = data["agents"]
    return {
        "totalAgents": len(agents),
        "activeAgents": sum(1 for agent in agents if agent["status"] == "ACTIVE"),
        "pendingInvites": sum(1 for agent in agents if agent["status"] == "INVITED"),
        "pendingReview": sum(1 for agent in agents if agent["status"] == "PENDING_REVIEW"),
        "declined": sum(1 for agent in agents if agent["status"] == "DECLINED"),
        "lastFiveAgents": [
            {
                "agentId": agent["id"],
                "agentName": agent["fullName"],
                "profileStatus": agent["status"],
                "userIsActive": agent["status"] != "DELETED",
                "assignments": [],
                "latestInvite": None,
                "metadata": {
                    "email": agent["email"],
                    "userCreatedAt": "",
                    "cognitoSub": "",
                    "serviceArea": agent["serviceArea"],
                    "statusReason": None,
                    "declineReason": agent["declineReason"],
                    "reviewedAt": agent["reviewedAt"],
                    "reviewedBy": None,
                    "formSubmittedAt": agent["formSubmittedAt"],
                    "passwordSetAt": None,
                    "approvedAt": None,
                    "approvedBy": None,
                },
            }
            for agent in agents[:5]
        ],
    }


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
