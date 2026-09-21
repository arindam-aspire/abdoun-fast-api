from __future__ import annotations

import math
import secrets
from datetime import timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_secret, verify_secret
from app.models.live_schema import (
    AgentInvite,
    AgentProfile,
    AgentServiceArea,
    Area,
    City,
    User,
    UserProfileChangeChallenge,
)
from app.schemas.agents import IDENTITY_DOCUMENT_MAX_BYTES, normalize_phone
from app.services.auth import assign_role, mark_password_set, normalize_username, utc_now
from app.services.media_urls import canonicalize_media_url, generate_presigned_put_url, resolve_readable_media_url
from app.services.notifications import EmailPurpose, send_email_notification, send_sms_notification
from app.services.user_agencies import REL_AGENT, agency_user_ids, ensure_user_agency_mapping, user_has_active_agency_mapping
from app.utils.api_response import raise_api_error
from app.utils.status_codes import (
    STATUS_BAD_REQUEST,
    STATUS_CONFLICT,
    STATUS_FORBIDDEN,
    STATUS_INTERNAL_SERVER_ERROR,
    STATUS_NOT_FOUND,
)


AGENT_STATUSES = {
    "ACTIVE",
    "INVITED",
    "PENDING_PASSWORD",
    "PENDING_REVIEW",
    "DECLINED",
    "INACTIVE",
    "DELETED",
}


def _empty_agent_list_page(*, page: int, page_size: int) -> dict:
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


def can_view_agent_directory(roles: tuple[str, ...]) -> bool:
    """Agency admins and super admins may browse the agent directory."""
    normalized = {role.casefold() for role in roles}
    if normalized & {"super_admin", "admin", "agency", "agency_admin"}:
        return True
    return False

INVITE_PURPOSE_ONBOARDING = "onboarding"
INVITE_PURPOSE_PASSWORD_SETUP = "password_setup"
INVITE_PURPOSE_LEGACY_ACCEPT = "legacy_accept"
AGENT_PASSWORD_CHALLENGE_PURPOSE = "agent_pw_setup"


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _frontend_base_url() -> str:
    return get_settings().frontend_base_url


def _invite_link(token: str) -> str:
    return f"{_frontend_base_url()}/agent-invite?token={token}"


def _password_setup_link(token: str) -> str:
    return f"{_frontend_base_url()}/agent-password-setup?token={token}"


def _invite_expiry() -> timedelta:
    return timedelta(seconds=get_settings().agent_invitation_ttl_seconds)


def _password_setup_expiry() -> timedelta:
    return timedelta(seconds=get_settings().agency_password_setup_ttl_seconds)


def _is_expired(expires_at) -> bool:
    current_time = utc_now()
    if expires_at.tzinfo is None:
        current_time = current_time.replace(tzinfo=None)
    return expires_at < current_time


def _pending_email_for_phone(phone: str) -> str:
    digits = normalize_phone(phone).lstrip("+")
    return f"pending+{digits}@agents.local"


def _load_service_areas(db: Session, agent_user_id: UUID) -> list[dict]:
    rows = db.execute(
        select(Area, City.name)
        .join(AgentServiceArea, AgentServiceArea.area_id == Area.id)
        .join(City, City.id == Area.city_id)
        .where(AgentServiceArea.agent_user_id == agent_user_id)
        .order_by(Area.name.asc())
    ).all()
    return [
        {
            "id": area.id,
            "name": area.name,
            "cityId": area.city_id,
            "cityName": city_name,
        }
        for area, city_name in rows
    ]


def _service_area_label(areas: list[dict]) -> str | None:
    if not areas:
        return None
    parts: list[str] = []
    for area in areas:
        city_name = area.get("cityName")
        if city_name:
            parts.append(f"{area['name']}, {city_name}")
        else:
            parts.append(str(area["name"]))
    return ", ".join(parts)


def _resolve_area_ids_from_service_area_label(db: Session, label: str) -> list[int]:
    """Resolve frontend free-text labels like '2nd Circle, Amman, 5th Circle, Amman' to area ids."""
    text = (label or "").strip()
    if not text:
        return []

    rows = db.execute(
        select(Area.id, Area.name, City.name).join(City, City.id == Area.city_id)
    ).all()
    if not rows:
        return []

    # Prefer "Area, City" matches, then bare area names. Longest-first avoids partial hits.
    candidates: list[tuple[str, int]] = []
    for area_id, area_name, city_name in rows:
        area_label = (area_name or "").strip()
        city_label = (city_name or "").strip()
        if not area_label:
            continue
        if city_label:
            candidates.append((f"{area_label}, {city_label}", int(area_id)))
        candidates.append((area_label, int(area_id)))
    candidates.sort(key=lambda item: len(item[0]), reverse=True)

    remaining = text
    found_ids: list[int] = []
    seen: set[int] = set()
    while remaining.strip():
        remaining = remaining.lstrip(" ,")
        if not remaining:
            break
        matched = False
        lowered = remaining.lower()
        for candidate_label, area_id in candidates:
            prefix = candidate_label.lower()
            if not lowered.startswith(prefix):
                continue
            # Require boundary after match (end or separator) so "1st Circle" does not steal "1st Circle Road".
            end = len(candidate_label)
            if end < len(remaining) and remaining[end] not in {",", " "}:
                continue
            if area_id not in seen:
                found_ids.append(area_id)
                seen.add(area_id)
            remaining = remaining[end:]
            matched = True
            break
        if not matched:
            # Skip an unrecognized token and continue scanning.
            next_comma = remaining.find(",")
            if next_comma < 0:
                break
            remaining = remaining[next_comma + 1 :]
    return found_ids


def _replace_agent_service_areas(db: Session, *, agent_user_id: UUID, area_ids: list[int]) -> list[dict]:
    unique_ids = sorted(set(area_ids))
    if not unique_ids:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="At least one service area is required",
        )

    found = db.execute(select(Area).where(Area.id.in_(unique_ids))).scalars().all()
    found_ids = {area.id for area in found}
    missing = [area_id for area_id in unique_ids if area_id not in found_ids]
    if missing:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="One or more service areas are invalid",
            details={"invalidAreaIds": missing},
        )

    db.execute(delete(AgentServiceArea).where(AgentServiceArea.agent_user_id == agent_user_id))
    for area_id in unique_ids:
        db.add(AgentServiceArea(agent_user_id=agent_user_id, area_id=area_id))
    db.flush()
    return _load_service_areas(db, agent_user_id)


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


def _latest_invite_for_user(db: Session, *, email: str | None, phone_number: str | None) -> AgentInvite | None:
    """Most recent invite for list display — includes used invites so invitedAt survives onboarding."""
    identity_filters = []
    if email:
        identity_filters.append(AgentInvite.email == normalize_username(email))
    if phone_number:
        identity_filters.append(AgentInvite.phone_number == normalize_phone(phone_number))
    if not identity_filters:
        return None

    return db.execute(
        select(AgentInvite)
        .where(
            AgentInvite.revoked_at.is_(None),
            or_(*identity_filters),
        )
        .order_by(AgentInvite.invited_at.desc().nullslast(), AgentInvite.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _revoke_active_invites(
    db: Session,
    *,
    actor_id: UUID,
    email: str | None = None,
    phone_number: str | None = None,
) -> None:
    conditions = [
        AgentInvite.revoked_at.is_(None),
        AgentInvite.is_used.is_(False),
    ]
    identity_filters = []
    if email:
        identity_filters.append(AgentInvite.email == normalize_username(email))
    if phone_number:
        identity_filters.append(AgentInvite.phone_number == normalize_phone(phone_number))
    if not identity_filters:
        return
    invites = db.execute(select(AgentInvite).where(*conditions, or_(*identity_filters))).scalars().all()
    for invite in invites:
        invite.revoked_at = utc_now()
        invite.revoked_by = actor_id


def _raise_duplicate_conflicts(
    db: Session,
    *,
    email: str | None,
    phone: str | None,
    exclude_user_id: UUID | None = None,
) -> None:
    if email:
        stmt = select(User).where(User.email == normalize_username(email))
        if exclude_user_id:
            stmt = stmt.where(User.id != exclude_user_id)
        if db.execute(stmt).scalar_one_or_none():
            raise_api_error(
                status_code=STATUS_CONFLICT,
                code="DUPLICATE_EMAIL",
                message="An account with this email already exists",
            )
    if phone:
        normalized_phone = normalize_phone(phone)
        stmt = select(User).where(User.phone_number == normalized_phone)
        if exclude_user_id:
            stmt = stmt.where(User.id != exclude_user_id)
        if db.execute(stmt).scalar_one_or_none():
            raise_api_error(
                status_code=STATUS_CONFLICT,
                code="DUPLICATE_PHONE",
                message="An account with this phone number already exists",
            )


def _create_agent_invite(
    db: Session,
    *,
    invited_by: UUID,
    purpose: str,
    email: str | None = None,
    phone_number: str | None = None,
) -> AgentInvite:
    _revoke_active_invites(db, actor_id=invited_by, email=email, phone_number=phone_number)
    invite = AgentInvite(
        id=uuid4(),
        email=normalize_username(email) if email else None,
        phone_number=normalize_phone(phone_number) if phone_number else None,
        purpose=purpose,
        invited_by=invited_by,
        token=secrets.token_urlsafe(32),
        expires_at=utc_now() + _invite_expiry(),
        is_used=False,
        invited_at=utc_now(),
    )
    db.add(invite)
    return invite


def _create_password_setup_challenge(db: Session, *, user: User, actor_id: UUID | None = None) -> str:
    token = secrets.token_urlsafe(32)
    challenge = UserProfileChangeChallenge(
        id=uuid4(),
        user_id=user.id,
        purpose=AGENT_PASSWORD_CHALLENGE_PURPOSE,
        new_value=str(user.id),
        otp_hash=hash_secret(token),
        expires_at=utc_now() + _password_setup_expiry(),
    )
    db.add(challenge)
    link = _password_setup_link(token)
    if user.email and not str(user.email).endswith("@agents.local"):
        send_email_notification(
            to_email=user.email,
            subject="Create your Abdoun agent password",
            body=f"Create your agent password. Dev password setup link: {link}",
            purpose=EmailPurpose.PASSWORD_RESET,
        )
    if user.phone_number:
        send_sms_notification(
            to_phone=user.phone_number,
            body=f"Create your Abdoun agent password. Dev link: {link}",
        )
    return token


def serialize_agent_invite(user: User, invite: AgentInvite) -> dict:
    invitation_url = _invite_link(invite.token)
    expiry = _iso(invite.expires_at)
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone_number or invite.phone_number or "",
        "status": "INVITED",
        "inviteLink": invitation_url,
        "invitedAt": _iso(invite.invited_at) or _iso(invite.created_at),
        "invitedBy": str(invite.invited_by),
        "purpose": invite.purpose,
        # Copy Invitation Link popup (snake_case + camelCase for clients)
        "invitation_id": str(invite.id),
        "invitation_url": invitation_url,
        "invitation_token": invite.token,
        "expiry": expiry,
        "invitationId": str(invite.id),
        "invitationUrl": invitation_url,
        "invitationToken": invite.token,
        "expiresAt": expiry,
    }


def serialize_agent_invitation_preview(
    db: Session,
    user: User,
    invite: AgentInvite,
    profile: AgentProfile | None,
) -> dict:
    service_areas = _load_service_areas(db, user.id) if profile else []
    return {
        "id": str(invite.id),
        "email": invite.email or user.email,
        "phone": invite.phone_number or user.phone_number or "",
        "fullName": user.full_name,
        "serviceArea": _service_area_label(service_areas) or (profile.service_area if profile else ""),
        "serviceAreas": service_areas,
        "position": profile.position if profile else None,
        "status": "EXPIRED" if _is_expired(invite.expires_at) else (profile.status if profile else "INVITED"),
        "purpose": invite.purpose or INVITE_PURPOSE_LEGACY_ACCEPT,
        "expiresAt": _iso(invite.expires_at),
        "alreadySubmitted": bool(profile and profile.form_submitted_at),
    }


def serialize_agent(
    db: Session,
    user: User,
    profile: AgentProfile | None,
    invited_by: str | None = None,
    invited_at=None,
) -> dict:
    service_areas = _load_service_areas(db, user.id) if profile else []
    return {
        "id": str(user.id),
        "email": user.email,
        "fullName": user.full_name,
        "phone": user.phone_number or "",
        "whatsappNumber": profile.whatsapp_number if profile else None,
        "serviceArea": _service_area_label(service_areas) or (profile.service_area if profile else ""),
        "serviceAreas": service_areas,
        "position": profile.position if profile else None,
        "identityDocumentUrl": resolve_readable_media_url(profile.identity_document_s3_link) if profile else None,
        "status": (profile.status if profile else "INVITED") or "INVITED",
        "invitedAt": _iso(invited_at),
        "invitedBy": invited_by,
        "formSubmittedAt": _iso(profile.form_submitted_at) if profile else None,
        "passwordSetAt": _iso(profile.password_set_at) if profile else None,
        "approvedAt": _iso(profile.approved_at) if profile else None,
        "approvedBy": str(profile.approved_by) if profile and profile.approved_by else None,
        "reviewedAt": _iso(profile.reviewed_at) if profile else None,
        "reviewedBy": str(profile.reviewed_by) if profile and profile.reviewed_by else None,
        "statusReason": profile.status_reason if profile else None,
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
    if not can_view_agent_directory(roles):
        return _empty_agent_list_page(page=page, page_size=page_size)

    is_super_admin = "super_admin" in {role.lower() for role in roles}
    if not is_super_admin and agency_id is None:
        return _empty_agent_list_page(page=page, page_size=page_size)

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
    sort_column = sort_columns.get(sort_by, User.created_at)
    stmt = stmt.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc().nullslast())

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(stmt.offset(offset).limit(page_size)).all()
    agents = []
    for user, profile in rows:
        invite = _latest_invite_for_user(db, email=user.email, phone_number=user.phone_number)
        agents.append(
            serialize_agent(
                db,
                user,
                profile,
                invited_by=str(invite.invited_by) if invite else None,
                invited_at=(invite.invited_at if invite else None) or (invite.created_at if invite else None),
            )
        )

    total_pages = math.ceil(total / page_size) if total else 1
    return {
        "agents": agents,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1,
        },
    }


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
        "pending_password": "PENDING_PASSWORD",
        "declined": "DECLINED",
        "deleted": "DELETED",
    }
    return mapping.get(value, status.strip().upper())


def invite_agent(
    db: Session,
    *,
    invited_by: UUID,
    agency_id: UUID | None,
    email: str | None = None,
    phone_number: str | None = None,
    full_name: str | None = None,
    service_area: str | None = None,
) -> dict:
    if agency_id is None:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Agency Admin must belong to an agency",
        )
    if not email and not phone_number:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Either email or phone_number is required",
        )

    normalized_email = normalize_username(email) if email else None
    normalized_phone = normalize_phone(phone_number) if phone_number else None
    _raise_duplicate_conflicts(db, email=normalized_email, phone=normalized_phone)

    lookup_conditions = []
    if normalized_email:
        lookup_conditions.append(User.email == normalized_email)
    if normalized_phone:
        lookup_conditions.append(User.phone_number == normalized_phone)
    user = db.execute(select(User).where(or_(*lookup_conditions))).scalar_one_or_none() if lookup_conditions else None

    if not user:
        user_email = normalized_email or _pending_email_for_phone(normalized_phone or "")
        user = User(
            id=uuid4(),
            full_name=full_name or (normalized_email or normalized_phone or "Invited Agent"),
            email=user_email,
            phone_number=normalized_phone,
            is_active=False,
            is_email_verified=False,
            is_phone_verified=False,
            preferred_language="en",
            agency_id=agency_id,
        )
        db.add(user)
        db.flush()
    else:
        if agency_id and not user.agency_id:
            user.agency_id = agency_id
        if full_name:
            user.full_name = full_name
        if normalized_phone and not user.phone_number:
            user.phone_number = normalized_phone
        user.is_active = False

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
            profile.deleted_at = None
        profile.status = "INVITED"
        profile.form_submitted_at = None
        profile.password_set_at = None

    invite = _create_agent_invite(
        db,
        invited_by=invited_by,
        purpose=INVITE_PURPOSE_ONBOARDING,
        email=user.email if not str(user.email).endswith("@agents.local") else normalized_email,
        phone_number=normalized_phone or user.phone_number,
    )
    if not invite.email:
        invite.email = user.email

    link = _invite_link(invite.token)
    if invite.email and not str(invite.email).endswith("@agents.local"):
        send_email_notification(
            to_email=invite.email,
            subject="Abdoun agent invitation",
            body=f"You have been invited as an agent. Complete onboarding using this dev link: {link}",
            purpose=EmailPurpose.AGENT_INVITATION,
        )
    if invite.phone_number:
        send_sms_notification(
            to_phone=invite.phone_number,
            body=f"You have been invited as an Abdoun agent. Dev onboarding link: {link}",
        )
    db.flush()
    return serialize_agent_invite(user, invite)


def get_agent_invitation_by_token(
    db: Session,
    token: str,
    *,
    allowed_purposes: set[str] | None = None,
) -> tuple[AgentInvite, User, AgentProfile | None]:
    invite = db.execute(select(AgentInvite).where(AgentInvite.token == token)).scalar_one_or_none()
    if not invite:
        raise_api_error(status_code=STATUS_NOT_FOUND, code="INVITATION_INVALID", message="Invitation not found")
    if invite.revoked_at is not None:
        raise_api_error(status_code=STATUS_BAD_REQUEST, code="INVITATION_INVALID", message="Invitation has been revoked")
    if invite.is_used:
        raise_api_error(status_code=STATUS_BAD_REQUEST, code="INVITATION_INVALID", message="Invitation has already been used")
    if _is_expired(invite.expires_at):
        raise_api_error(status_code=STATUS_BAD_REQUEST, code="INVITATION_EXPIRED", message="Invitation link has expired")

    purpose = invite.purpose or INVITE_PURPOSE_LEGACY_ACCEPT
    if allowed_purposes is not None and purpose not in allowed_purposes:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVITATION_INVALID",
            message=f"Invitation is not valid for this action (purpose={purpose})",
        )

    user = None
    if invite.email:
        user = db.execute(select(User).where(User.email == invite.email)).scalar_one_or_none()
    if not user and invite.phone_number:
        user = db.execute(select(User).where(User.phone_number == invite.phone_number)).scalar_one_or_none()
    if not user:
        raise_api_error(status_code=STATUS_NOT_FOUND, code="INVITATION_INVALID", message="Invited agent account not found")
    return invite, user, db.get(AgentProfile, user.id)


def validate_agent_invitation(db: Session, *, token: str) -> dict:
    invite, user, profile = get_agent_invitation_by_token(db, token)
    return serialize_agent_invitation_preview(db, user, invite, profile)


def submit_agent_onboarding(
    db: Session,
    *,
    token: str,
    full_name: str,
    phone: str,
    service_area_ids: list[int] | None = None,
    service_area: str | None = None,
    position: str | None = None,
    identity_document_url: str | None = None,
    whatsapp_number: str | None = None,
    email: str | None = None,  # Ignored — email always comes from the invitation record
) -> dict:
    invite, user, profile = get_agent_invitation_by_token(
        db,
        token,
        allowed_purposes={INVITE_PURPOSE_ONBOARDING, INVITE_PURPOSE_LEGACY_ACCEPT},
    )
    if profile and profile.form_submitted_at:
        raise_api_error(
            status_code=STATUS_CONFLICT,
            code="VALIDATION_ERROR",
            message="Onboarding form has already been submitted",
        )

    # Never trust client-supplied email; bind identity to the invitation record.
    _ = email  # retained for backward-compatible callers; intentionally unused
    invited_email = invite.email or user.email
    if not invited_email:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invitation does not have an email address",
        )
    normalized_email = normalize_username(invited_email)
    normalized_phone = normalize_phone(phone)
    _raise_duplicate_conflicts(db, email=normalized_email, phone=normalized_phone, exclude_user_id=user.id)

    area_ids = list(service_area_ids or [])
    free_text_service_area = (service_area or "").strip() or None
    if not area_ids and free_text_service_area:
        area_ids = _resolve_area_ids_from_service_area_label(db, free_text_service_area)
        if not area_ids:
            raise_api_error(
                status_code=STATUS_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="One or more service areas are invalid",
                details={"serviceArea": free_text_service_area},
            )
    if not area_ids:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="At least one service area is required",
        )

    user.full_name = full_name
    user.email = normalized_email
    user.phone_number = normalized_phone
    user.is_active = False

    if not profile:
        profile = AgentProfile(user_id=user.id)
        db.add(profile)
        db.flush()

    service_areas = _replace_agent_service_areas(db, agent_user_id=user.id, area_ids=area_ids)
    # Prefer client free-text label when provided; otherwise derive from persisted areas.
    profile.service_area = free_text_service_area or _service_area_label(service_areas)
    profile.whatsapp_number = whatsapp_number
    profile.position = position
    if identity_document_url:
        profile.identity_document_s3_link = canonicalize_media_url(identity_document_url) or identity_document_url
    else:
        profile.identity_document_s3_link = None
    profile.status = "PENDING_PASSWORD"
    profile.form_submitted_at = utc_now()
    profile.deleted_at = None
    profile.decline_reason = None

    invite.is_used = True
    invite.email = normalized_email
    invite.phone_number = normalized_phone

    password_token = _create_password_setup_challenge(db, user=user, actor_id=invite.invited_by)
    db.flush()
    return {
        "id": str(user.id),
        "email": user.email,
        "fullName": user.full_name,
        "phone": user.phone_number or "",
        "whatsappNumber": profile.whatsapp_number,
        "serviceArea": profile.service_area,
        "serviceAreas": service_areas,
        "position": profile.position,
        "status": profile.status,
        "formSubmittedAt": _iso(profile.form_submitted_at),
        "passwordSetupLink": _password_setup_link(password_token),
    }


def complete_agent_password_setup(db: Session, *, token: str, password: str) -> dict:
    challenges = db.execute(
        select(UserProfileChangeChallenge)
        .where(UserProfileChangeChallenge.purpose == AGENT_PASSWORD_CHALLENGE_PURPOSE)
        .order_by(UserProfileChangeChallenge.created_at.desc())
    ).scalars().all()
    challenge = next((item for item in challenges if verify_secret(token, item.otp_hash)), None)
    if not challenge:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVITATION_INVALID",
            message="Password creation link is invalid",
        )
    if _is_expired(challenge.expires_at):
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVITATION_EXPIRED",
            message="Password creation link has expired",
        )

    user = db.get(User, challenge.user_id)
    profile = db.get(AgentProfile, challenge.user_id) if user else None
    if not user or not profile:
        raise_api_error(status_code=STATUS_NOT_FOUND, code="INVITATION_INVALID", message="Agent account not found")

    user.password_hash = hash_secret(password)
    user.is_active = True
    user.is_email_verified = True
    # Password set does not approve the agent — admin must activate via status update.
    profile.status = "PENDING_REVIEW"
    profile.deleted_at = None
    profile.password_set_at = utc_now()
    profile.approved_at = None
    profile.approved_by = None
    profile.reviewed_at = None
    profile.reviewed_by = None
    profile.decline_reason = None
    profile.status_reason = None
    mark_password_set(db, user)
    challenge.expires_at = utc_now()
    db.flush()
    return serialize_agent(db, user, profile)


def accept_agent_invitation(db: Session, *, token: str, password: str) -> dict:
    """Backward-compatible combined accept for legacy invitation links."""
    invite, user, profile = get_agent_invitation_by_token(db, token)
    purpose = invite.purpose or INVITE_PURPOSE_LEGACY_ACCEPT
    if purpose == INVITE_PURPOSE_ONBOARDING:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVITATION_INVALID",
            message="This invitation requires onboarding form submission before password setup",
        )
    if purpose not in {INVITE_PURPOSE_LEGACY_ACCEPT, INVITE_PURPOSE_PASSWORD_SETUP}:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVITATION_INVALID",
            message="Invitation is not valid for password acceptance",
        )

    user.password_hash = hash_secret(password)
    user.is_active = True
    user.is_email_verified = True
    invite.is_used = True

    if not profile:
        profile = AgentProfile(user_id=user.id)
        db.add(profile)
    # Legacy accept also waits for admin approval — ACTIVE only via PATCH status.
    profile.status = "PENDING_REVIEW"
    profile.deleted_at = None
    profile.password_set_at = utc_now()
    profile.approved_by = None
    profile.approved_at = None
    profile.reviewed_by = None
    profile.reviewed_at = None
    profile.decline_reason = None
    profile.status_reason = None
    mark_password_set(db, user)
    db.flush()
    return serialize_agent(db, user, profile, invited_by=str(invite.invited_by), invited_at=invite.invited_at)


def create_agent_document_upload(
    db: Session,
    *,
    token: str,
    file_name: str,
    content_type: str,
    file_size: int,
) -> dict:
    """Presigned upload for invited (unauthenticated) agents via invitation token."""
    invite, _user, _profile = get_agent_invitation_by_token(
        db,
        token,
        allowed_purposes={INVITE_PURPOSE_ONBOARDING, INVITE_PURPOSE_LEGACY_ACCEPT},
    )
    if file_size > IDENTITY_DOCUMENT_MAX_BYTES:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Identity document must be 5 MB or smaller",
        )

    safe_file_name = PurePosixPath(file_name).name
    object_key = f"invitation/identity_documents/{invite.id}/{uuid4()}-{safe_file_name}"

    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    if bucket:
        presigned = generate_presigned_put_url(object_key)
        if not presigned: 
            raise_api_error(
                status_code=STATUS_INTERNAL_SERVER_ERROR,
                code="UPLOAD_ERROR",
                message="Could not generate upload URL",
            )
        return {
            "upload_url": presigned["upload_url"],
            "object_key": presigned["object_key"],
            "file_url": presigned["file_url"],
            "readable_url": presigned["readable_url"],
            "signed_read_url": presigned["signed_read_url"],
            "mode": "s3",
            "content_type": content_type,
            "file_size": file_size,
            "expires_in": presigned["expires_in"],
            "readable_expires_in": presigned["readable_expires_in"],
        }

    dev_url = f"dev://uploads/{object_key}"
    return {
        "upload_url": dev_url,
        "object_key": object_key,
        "file_url": dev_url,
        "readable_url": dev_url,
        "signed_read_url": dev_url,
        "mode": "log",
        "content_type": content_type,
        "file_size": file_size,
    }


def manual_onboard_agent(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone: str,
    service_area_ids: list[int] | None = None,
    service_area: str | None = None,
    position: str | None = None,
    identity_document_url: str | None = None,
    actor_id: UUID,
    agency_id: UUID | None,
    whatsapp_number: str | None = None,
) -> dict:
    if agency_id is None:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Agency Admin must belong to an agency",
        )
    normalized_email = normalize_username(email)
    normalized_phone = normalize_phone(phone)
    _raise_duplicate_conflicts(db, email=normalized_email, phone=normalized_phone)

    area_ids = list(service_area_ids or [])
    free_text_service_area = (service_area or "").strip() or None
    if not area_ids and free_text_service_area:
        area_ids = _resolve_area_ids_from_service_area_label(db, free_text_service_area)
        if not area_ids:
            raise_api_error(
                status_code=STATUS_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="One or more service areas are invalid",
                details={"serviceArea": free_text_service_area},
            )
    if not area_ids:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="At least one service area is required",
        )

    user = User(
        id=uuid4(),
        full_name=full_name,
        email=normalized_email,
        phone_number=normalized_phone,
        is_active=False,
        is_email_verified=False,
        is_phone_verified=False,
        preferred_language="en",
        agency_id=agency_id,
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
    stored_identity = None
    if identity_document_url:
        stored_identity = canonicalize_media_url(identity_document_url) or identity_document_url
    profile = AgentProfile(
        user_id=user.id,
        whatsapp_number=whatsapp_number,
        position=position,
        identity_document_s3_link=stored_identity,
        status="PENDING_PASSWORD",
        form_submitted_at=utc_now(),
        # Manual onboard still requires password setup + admin approval before ACTIVE.
        reviewed_by=None,
        reviewed_at=None,
        approved_by=None,
        approved_at=None,
        decline_reason=None,
        status_reason=None,
    )
    db.add(profile)
    db.flush()
    service_areas = _replace_agent_service_areas(db, agent_user_id=user.id, area_ids=area_ids)
    profile.service_area = free_text_service_area or _service_area_label(service_areas)

    password_token = _create_password_setup_challenge(db, user=user, actor_id=actor_id)
    temporary_password = secrets.token_urlsafe(10)
    user.password_hash = hash_secret(temporary_password)
    db.flush()
    setup_link = _password_setup_link(password_token)
    return {
        "id": str(user.id),
        "email": user.email,
        "fullName": user.full_name,
        "phone": user.phone_number or "",
        "whatsappNumber": profile.whatsapp_number,
        "serviceArea": profile.service_area,
        "serviceAreas": service_areas,
        "position": profile.position,
        "identityDocumentUrl": resolve_readable_media_url(profile.identity_document_s3_link),
        "status": profile.status,
        "temporaryPassword": temporary_password,
        "temporary_password": temporary_password,
        "inviteLink": setup_link,
        "passwordSetupLink": setup_link,
    }


def resend_agent_invitation(
    db: Session,
    *,
    agent_id: UUID,
    actor_id: UUID,
    agency_id: UUID | None,
) -> dict:
    if agency_id is None:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Agency Admin must belong to an agency",
        )
    user = db.get(User, agent_id)
    profile = db.get(AgentProfile, agent_id)
    if not user or not profile:
        raise_api_error(status_code=STATUS_NOT_FOUND, code="VALIDATION_ERROR", message="Agent not found")
    if not _agent_in_agency(db, user=user, agency_id=agency_id):
        raise_api_error(status_code=STATUS_FORBIDDEN, code="VALIDATION_ERROR", message="Agent is outside the agency")

    if profile.status == "PENDING_PASSWORD" or profile.form_submitted_at:
        password_token = _create_password_setup_challenge(db, user=user, actor_id=actor_id)
        password_url = _password_setup_link(password_token)
        expiry = _iso(utc_now() + _password_setup_expiry())
        db.flush()
        return {
            "id": str(user.id),
            "email": user.email,
            "status": profile.status,
            "passwordSetupLink": password_url,
            "invitedBy": str(actor_id),
            "invitation_id": None,
            "invitation_url": password_url,
            "invitation_token": password_token,
            "expiry": expiry,
            "invitationId": None,
            "invitationUrl": password_url,
            "invitationToken": password_token,
            "expiresAt": expiry,
        }

    invite = _create_agent_invite(
        db,
        invited_by=actor_id,
        purpose=INVITE_PURPOSE_ONBOARDING,
        email=None if str(user.email).endswith("@agents.local") else user.email,
        phone_number=user.phone_number,
    )
    if not invite.email:
        invite.email = user.email
    profile.status = "INVITED"
    link = _invite_link(invite.token)
    if invite.email and not str(invite.email).endswith("@agents.local"):
        send_email_notification(
            to_email=invite.email,
            subject="Abdoun agent invitation",
            body=f"You have been invited as an agent. Dev onboarding link: {link}",
            purpose=EmailPurpose.AGENT_INVITATION,
        )
    if user.phone_number:
        send_sms_notification(
            to_phone=user.phone_number,
            body=f"Abdoun agent invitation. Dev onboarding link: {link}",
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
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Agency Admin must belong to an agency",
        )
    user = db.get(User, agent_id)
    profile = db.get(AgentProfile, agent_id)
    if not user or not profile:
        raise_api_error(status_code=STATUS_NOT_FOUND, code="VALIDATION_ERROR", message="Agent not found")
    if not _agent_in_agency(db, user=user, agency_id=agency_id):
        raise_api_error(status_code=STATUS_FORBIDDEN, code="VALIDATION_ERROR", message="Agent is outside the agency")
    profile.status = "DELETED"
    profile.deleted_at = utc_now()
    profile.deleted_by = actor_id
    user.is_active = False
    _revoke_active_invites(db, actor_id=actor_id, email=user.email, phone_number=user.phone_number)


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
        "pendingPassword": sum(1 for agent in agents if agent["status"] == "PENDING_PASSWORD"),
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
                    "passwordSetAt": agent.get("passwordSetAt"),
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
        raise_api_error(status_code=STATUS_BAD_REQUEST, code="VALIDATION_ERROR", message="Invalid agent status")

    user = db.get(User, agent_id)
    profile = db.get(AgentProfile, agent_id)
    if not user or not profile:
        raise_api_error(status_code=STATUS_NOT_FOUND, code="VALIDATION_ERROR", message="Agent not found")
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
        raise_api_error(status_code=STATUS_FORBIDDEN, code="VALIDATION_ERROR", message="Agent is outside the agency")

    profile.status = normalized_status
    profile.reviewed_by = actor_id
    profile.reviewed_at = utc_now()
    profile.status_reason = reason
    if normalized_status == "ACTIVE":
        profile.approved_by = actor_id
        profile.approved_at = utc_now()
        profile.decline_reason = None
        user.is_active = True
    elif normalized_status == "DECLINED":
        profile.decline_reason = reason
        profile.approved_by = None
        profile.approved_at = None
    elif normalized_status == "PENDING_REVIEW":
        profile.approved_by = None
        profile.approved_at = None
        profile.decline_reason = None
    elif normalized_status in {"INACTIVE", "DELETED"}:
        # Keep approval history; account access follows inactive/deleted status.
        if normalized_status == "INACTIVE":
            user.is_active = False
    return serialize_agent(db, user, profile)
