from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.live_schema import Lead, LeadMessage, LeadNote, LeadStatusHistory, PropertyListingSubmission, Role, User, UserRole
from app.schemas.leads import LeadCreate
from app.services.audit import record_activity
from app.services.notifications import create_in_app_notification, send_email_notification, send_sms_notification
from app.services.public_properties import get_public_submission_or_404, pagination_meta, serialize_property_listing
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_FORBIDDEN, STATUS_NOT_FOUND


AGENCY_ADMIN_ROLE = "admin"
SUPER_ADMIN_ROLE = "super_admin"
AGENT_ROLE = "agent"
REGISTERED_USER_ROLE = "registered_user"
LEAD_STATUSES = {"NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def primary_role(roles: tuple[str, ...]) -> str | None:
    if SUPER_ADMIN_ROLE in roles:
        return SUPER_ADMIN_ROLE
    if AGENCY_ADMIN_ROLE in roles:
        return AGENCY_ADMIN_ROLE
    if AGENT_ROLE in roles:
        return AGENT_ROLE
    if REGISTERED_USER_ROLE in roles:
        return REGISTERED_USER_ROLE
    return roles[0] if roles else None


def generate_lead_number(db: Session) -> str:
    today = utc_now().strftime("%Y%m%d")
    count_today = db.execute(
        select(func.count()).where(Lead.lead_number.like(f"LD-{today}-%"))
    ).scalar() or 0
    return f"LD-{today}-{count_today + 1:05d}"


def get_lead_or_404(db: Session, lead_id: UUID) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Lead not found")
    return lead


def user_role_names(db: Session, user_id: UUID) -> set[str]:
    return set(
        db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        ).scalars().all()
    )


def user_has_role(db: Session, user_id: UUID, role_name: str) -> bool:
    return role_name in user_role_names(db, user_id)


def _assigned_agent_id(submission: PropertyListingSubmission) -> UUID | None:
    workflow = (submission.payload or {}).get("_workflow") or {}
    agent_id = workflow.get("assigned_agent_id")
    if not agent_id:
        return None
    try:
        return UUID(str(agent_id))
    except ValueError:
        return None


def _lead_property_submission(db: Session, lead: Lead) -> tuple[PropertyListingSubmission, User | None] | None:
    if not lead.property_id:
        return None
    try:
        return get_public_submission_or_404(db, lead.property_id)
    except HTTPException:
        return None


def _agency_admins(db: Session, agency_id: UUID | None) -> list[User]:
    if not agency_id:
        return []
    return db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.agency_id == agency_id,
            User.is_active.is_(True),
            Role.name == AGENCY_ADMIN_ROLE,
        )
    ).scalars().all()


def _can_access_lead(db: Session, lead: Lead, *, user_id: UUID, roles: tuple[str, ...], agency_id: UUID | None) -> bool:
    if SUPER_ADMIN_ROLE in roles:
        return True
    if lead.user_id == user_id or lead.assigned_agent_id == user_id or lead.created_by_agent_id == user_id or lead.created_by_admin_id == user_id:
        return True
    if AGENCY_ADMIN_ROLE in roles and agency_id:
        submission_match = _lead_property_submission(db, lead)
        submitter = submission_match[1] if submission_match else None
        if submitter and submitter.agency_id == agency_id:
            return True
        if lead.assigned_agent_id:
            agent = db.get(User, lead.assigned_agent_id)
            if agent and agent.agency_id == agency_id:
                return True
    return False


def assert_can_access_lead(db: Session, lead: Lead, *, user_id: UUID, roles: tuple[str, ...], agency_id: UUID | None) -> None:
    if not _can_access_lead(db, lead, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def _lead_query_for_context(db: Session, *, user_id: UUID, roles: tuple[str, ...], agency_id: UUID | None):
    stmt = select(Lead).order_by(Lead.updated_at.desc(), Lead.created_at.desc())
    if SUPER_ADMIN_ROLE in roles:
        return stmt
    if AGENCY_ADMIN_ROLE in roles and agency_id:
        agency_user_ids = select(User.id).where(User.agency_id == agency_id)
        property_ids = (
            select(PropertyListingSubmission.property_id)
            .join(User, User.id == PropertyListingSubmission.submitted_by)
            .where(User.agency_id == agency_id, PropertyListingSubmission.property_id.is_not(None))
        )
        return stmt.where(
            or_(
                Lead.assigned_agent_id.in_(agency_user_ids),
                Lead.created_by_agent_id.in_(agency_user_ids),
                Lead.created_by_admin_id == user_id,
                Lead.property_id.in_(property_ids),
            )
        )
    if AGENT_ROLE in roles:
        return stmt.where(or_(Lead.assigned_agent_id == user_id, Lead.created_by_agent_id == user_id))
    return stmt.where(Lead.user_id == user_id)


def record_status_history(
    db: Session,
    *,
    lead: Lead,
    from_status: str | None,
    to_status: str,
    actor_user_id: UUID | None,
    actor_role: str | None,
    reason: str | None = None,
) -> LeadStatusHistory:
    history = LeadStatusHistory(
        id=uuid4(),
        lead_id=lead.id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        reason=reason,
        changed_at=utc_now(),
    )
    db.add(history)
    return history


def create_lead(db: Session, *, payload: LeadCreate, user_id: UUID | None = None) -> Lead:
    submission, submitter = get_public_submission_or_404(db, payload.property_hash)
    property_id = submission.property_id or submission.id
    assigned_agent_id = _assigned_agent_id(submission)
    lead = Lead(
        id=uuid4(),
        property_id=property_id,
        user_id=user_id,
        inquiry_type=payload.inquiry_type,
        message=payload.message,
        status="NEW",
        source=payload.source,
        assigned_agent_id=assigned_agent_id,
        last_activity_at=utc_now(),
        lead_number=generate_lead_number(db),
        external_owner_name=payload.contact_name,
        external_owner_phone=payload.contact_phone,
        external_owner_email=str(payload.contact_email) if payload.contact_email else None,
        external_property_name=((submission.payload or {}).get("basic_information") or {}).get("title"),
        communication_mode=payload.communication_mode,
    )
    db.add(lead)
    record_status_history(db, lead=lead, from_status=None, to_status="NEW", actor_user_id=user_id, actor_role=None)
    record_activity(
        db,
        activity_type="lead_created",
        message=f"Lead {lead.lead_number} created",
        user_id=user_id,
        property_id=property_id,
    )

    notify_users: list[User] = []
    if assigned_agent_id:
        agent = db.get(User, assigned_agent_id)
        if agent:
            notify_users.append(agent)
    if submitter:
        notify_users.extend(_agency_admins(db, submitter.agency_id))
    seen: set[UUID] = set()
    for recipient in notify_users:
        if recipient.id in seen:
            continue
        seen.add(recipient.id)
        create_in_app_notification(
            db,
            recipient_user_id=recipient.id,
            actor_user_id=user_id,
            type_key="lead_created",
            title="New property inquiry",
            message=f"New inquiry received for lead {lead.lead_number}.",
            data={"lead_id": str(lead.id), "property_id": str(property_id)},
        )
        send_email_notification(
            to_email=recipient.email,
            subject="New property inquiry",
            body=f"New inquiry received for lead {lead.lead_number}.",
        )
        if recipient.phone_number:
            send_sms_notification(
                to_phone=recipient.phone_number,
                body=f"New inquiry received for lead {lead.lead_number}.",
            )
    return lead


def serialize_lead(db: Session, lead: Lead) -> dict[str, Any]:
    submission_match = _lead_property_submission(db, lead)
    property_payload = None
    if submission_match:
        property_payload = serialize_property_listing(db, submission_match[0], submitter=submission_match[1])
    return {
        "id": str(lead.id),
        "lead_number": lead.lead_number,
        "property_id": str(lead.property_id) if lead.property_id else None,
        "property_hash": property_payload.get("property_hash") if property_payload else None,
        "property": property_payload,
        "user_id": str(lead.user_id) if lead.user_id else None,
        "inquiry_type": lead.inquiry_type,
        "message": lead.message,
        "status": lead.status,
        "source": lead.source,
        "assigned_agent_id": str(lead.assigned_agent_id) if lead.assigned_agent_id else None,
        "assigned_by_admin_id": str(lead.assigned_by_admin_id) if lead.assigned_by_admin_id else None,
        "last_activity_at": iso(lead.last_activity_at),
        "request_close_at": iso(lead.request_close_at),
        "closed_at": iso(lead.closed_at),
        "closed_by_admin_id": str(lead.closed_by_admin_id) if lead.closed_by_admin_id else None,
        "contact_name": lead.external_owner_name,
        "contact_phone": lead.external_owner_phone,
        "contact_email": lead.external_owner_email,
        "external_property_name": lead.external_property_name,
        "communication_mode": lead.communication_mode,
        "created_by_agent_id": str(lead.created_by_agent_id) if lead.created_by_agent_id else None,
        "created_by_admin_id": str(lead.created_by_admin_id) if lead.created_by_admin_id else None,
        "created_at": iso(lead.created_at),
        "updated_at": iso(lead.updated_at),
    }


def list_leads_for_context(
    db: Session,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
    page: int,
    page_size: int,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = _lead_query_for_context(db, user_id=user_id, roles=roles, agency_id=agency_id)
    if status:
        stmt = stmt.where(Lead.status == status)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    leads = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return [serialize_lead(db, lead) for lead in leads], pagination_meta(total, page, page_size)


def assign_lead(
    db: Session,
    *,
    lead: Lead,
    agent_id: UUID | None,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> Lead:
    if AGENCY_ADMIN_ROLE not in actor_roles and SUPER_ADMIN_ROLE not in actor_roles:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin or Super Admin can assign leads")
    if agent_id:
        agent = db.get(User, agent_id)
        if not agent or not agent.is_active or not user_has_role(db, agent.id, AGENT_ROLE):
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agent not found")
        if AGENCY_ADMIN_ROLE in actor_roles and actor_agency_id and agent.agency_id != actor_agency_id:
            raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent is outside the agency")
    lead.assigned_agent_id = agent_id
    lead.assigned_by_admin_id = actor_user_id
    lead.status = "IN_PROGRESS" if agent_id and lead.status == "NEW" else lead.status
    lead.last_activity_at = utc_now()
    record_activity(
        db,
        activity_type="lead_assigned",
        message=f"Lead {lead.lead_number} assigned",
        user_id=actor_user_id,
        property_id=lead.property_id,
    )
    if agent_id:
        create_in_app_notification(
            db,
            recipient_user_id=agent_id,
            actor_user_id=actor_user_id,
            type_key="lead_assigned",
            title="Lead assigned",
            message=f"Lead {lead.lead_number} has been assigned to you.",
            data={"lead_id": str(lead.id)},
        )
    return lead


def update_lead_status(
    db: Session,
    *,
    lead: Lead,
    status: str,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    reason: str | None = None,
) -> Lead:
    if status not in LEAD_STATUSES:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid lead status")
    if lead.status == "CLOSED":
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Closed leads cannot be changed")
    if status == "CLOSED" and AGENCY_ADMIN_ROLE not in actor_roles and SUPER_ADMIN_ROLE not in actor_roles:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin can close a lead")
    if status == "REQUEST_FOR_CLOSE" and AGENT_ROLE not in actor_roles and AGENCY_ADMIN_ROLE not in actor_roles and SUPER_ADMIN_ROLE not in actor_roles:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")
    previous_status = lead.status
    lead.status = status
    lead.last_activity_at = utc_now()
    if status == "REQUEST_FOR_CLOSE":
        lead.request_close_at = utc_now()
    if status == "CLOSED":
        lead.closed_at = utc_now()
        lead.closed_by_admin_id = actor_user_id
    record_status_history(
        db,
        lead=lead,
        from_status=previous_status,
        to_status=status,
        actor_user_id=actor_user_id,
        actor_role=primary_role(actor_roles),
        reason=reason,
    )
    record_activity(
        db,
        activity_type="lead_status_updated",
        message=f"Lead {lead.lead_number} moved from {previous_status} to {status}",
        user_id=actor_user_id,
        property_id=lead.property_id,
    )
    return lead


def add_lead_note(db: Session, *, lead: Lead, author_user_id: UUID, note: str) -> LeadNote:
    record = LeadNote(
        id=uuid4(),
        lead_id=lead.id,
        author_user_id=author_user_id,
        note=note,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    lead.last_activity_at = utc_now()
    db.add(record)
    return record


def add_lead_message(
    db: Session,
    *,
    lead: Lead,
    sender_user_id: UUID,
    recipient_user_id: UUID | None,
    message: str,
    channel: str,
) -> LeadMessage:
    persisted_channel = "EMAIL" if channel == "EMAIL" else "IN_APP"
    record = LeadMessage(
        id=uuid4(),
        lead_id=lead.id,
        sender_user_id=sender_user_id,
        recipient_user_id=recipient_user_id,
        message=message,
        channel=persisted_channel,
        delivery_state="logged" if channel in {"EMAIL", "SMS"} else "created",
        created_at=utc_now(),
    )
    lead.last_activity_at = utc_now()
    db.add(record)
    if recipient_user_id:
        create_in_app_notification(
            db,
            recipient_user_id=recipient_user_id,
            actor_user_id=sender_user_id,
            type_key="lead_message",
            title="Lead message",
            message=message,
            data={"lead_id": str(lead.id)},
        )
        recipient = db.get(User, recipient_user_id)
        if recipient and channel == "EMAIL":
            send_email_notification(to_email=recipient.email, subject="Lead message", body=message)
        if recipient and channel == "SMS" and recipient.phone_number:
            send_sms_notification(to_phone=recipient.phone_number, body=message)
    return record

