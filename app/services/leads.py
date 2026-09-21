from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.live_schema import ActivityLog, Lead, LeadCloseRequest, LeadMessage, LeadNote, LeadStatusHistory, PropertyListingSubmission, Role, User, UserRole
from app.schemas.leads import LeadCreate
from app.services.audit import record_activity
from app.services.notifications import EmailPurpose, create_in_app_notification, send_email_notification, send_sms_notification
from app.services.property_submissions import DEAL_CLOSED_STATUS
from app.services.public_properties import get_public_submission_or_404, pagination_meta, serialize_property_listing
from app.services.user_agencies import REL_AGENCY_ADMIN, REL_AGENT, active_agency_ids_for_user, agency_user_ids, agency_users_with_role, user_has_active_agency_mapping
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_CONFLICT, STATUS_FORBIDDEN, STATUS_NOT_FOUND


AGENCY_ADMIN_ROLE = "admin"
SUPER_ADMIN_ROLE = "super_admin"
AGENT_ROLE = "agent"
REGISTERED_USER_ROLE = "registered_user"
LEAD_STATUSES = {"NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED"}
CLOSE_REQUEST_PENDING = "PENDING"
CLOSE_REQUEST_APPROVED = "APPROVED"
CLOSE_REQUEST_REJECTED = "REJECTED"
CLOSE_REQUEST_CANCELED = "CANCELED"


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


def get_lead_for_update_or_404(db: Session, lead_id: UUID) -> Lead:
    lead = db.execute(
        select(Lead)
        .where(Lead.id == lead_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
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
        return db.execute(
            select(PropertyListingSubmission, User)
            .join(User, User.id == PropertyListingSubmission.submitted_by)
            .where(
                PropertyListingSubmission.property_id == lead.property_id,
                PropertyListingSubmission.deleted_at.is_(None),
            )
            .order_by(PropertyListingSubmission.updated_at.desc())
        ).first()


def _submission_agency_id(submission: PropertyListingSubmission | None, submitter: User | None = None) -> UUID | None:
    if not submission:
        return None
    return submission.agency_id or (submitter.agency_id if submitter else None)


def _agency_admins(db: Session, agency_id: UUID | None) -> list[User]:
    if not agency_id:
        return []
    mapped_admins = agency_users_with_role(db, agency_id=agency_id, role_name=AGENCY_ADMIN_ROLE)
    legacy_admins = db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.agency_id == agency_id, User.is_active.is_(True), Role.name == AGENCY_ADMIN_ROLE)
    ).scalars().all()
    by_id = {user.id: user for user in mapped_admins}
    by_id.update({user.id: user for user in legacy_admins})
    return list(by_id.values())


def _can_access_lead(db: Session, lead: Lead, *, user_id: UUID, roles: tuple[str, ...], agency_id: UUID | None) -> bool:
    if SUPER_ADMIN_ROLE in roles:
        return True
    if lead.user_id == user_id or lead.assigned_agent_id == user_id or lead.created_by_agent_id == user_id or lead.created_by_admin_id == user_id:
        return True
    if AGENCY_ADMIN_ROLE in roles and agency_id:
        submission_match = _lead_property_submission(db, lead)
        submission = submission_match[0] if submission_match else None
        submitter = submission_match[1] if submission_match else None
        if _submission_agency_id(submission, submitter) == agency_id:
            return True
        if lead.assigned_agent_id:
            agent = db.get(User, lead.assigned_agent_id)
            has_mapping = user_has_active_agency_mapping(
                db,
                user_id=lead.assigned_agent_id,
                agency_id=agency_id,
                relationship_type=REL_AGENT,
            )
            if agent and (has_mapping or agent.agency_id == agency_id):
                return True
    return False


def assert_can_access_lead(db: Session, lead: Lead, *, user_id: UUID, roles: tuple[str, ...], agency_id: UUID | None) -> None:
    if not _can_access_lead(db, lead, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def assert_assigned_agent_can_request_close(lead: Lead, *, user_id: UUID, roles: tuple[str, ...]) -> None:
    if set(roles) != {AGENT_ROLE} or lead.assigned_agent_id != user_id:
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="Only the assigned agent can request lead closure",
        )


def _user_agency_ids(
    db: Session,
    user_id: UUID | None,
    *,
    relationship_types: tuple[str, ...],
) -> set[UUID]:
    if not user_id:
        return set()
    ids = set(
        active_agency_ids_for_user(
            db,
            user_id,
            relationship_types=relationship_types,
        )
    )
    user = db.get(User, user_id)
    if user and user.agency_id:
        ids.add(user.agency_id)
    return ids


def lead_belongs_to_agency(db: Session, lead: Lead, agency_id: UUID) -> bool:
    submission_match = _lead_property_submission(db, lead)
    if submission_match:
        submission_agency_id = _submission_agency_id(submission_match[0], submission_match[1])
        if submission_agency_id is not None:
            return submission_agency_id == agency_id

    related_users = (
        (lead.assigned_agent_id, (REL_AGENT,)),
        (lead.created_by_agent_id, (REL_AGENT,)),
        (lead.created_by_admin_id, (REL_AGENCY_ADMIN,)),
    )
    return any(
        agency_id in _user_agency_ids(db, user_id, relationship_types=relationship_types)
        for user_id, relationship_types in related_users
    )


def assert_admin_can_review_close(
    db: Session,
    lead: Lead,
    *,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> None:
    if SUPER_ADMIN_ROLE in actor_roles:
        return
    if AGENCY_ADMIN_ROLE not in actor_roles:
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="Only an Agency Admin or Super Admin can review lead closure",
        )
    if actor_agency_id is None or not lead_belongs_to_agency(db, lead, actor_agency_id):
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="The lead is outside the administrator's agency",
        )


def can_view_lead_internal_notes(lead: Lead, *, user_id: UUID, roles: tuple[str, ...]) -> bool:
    """Internal notes are visible only to admins and the assigned agent."""
    if SUPER_ADMIN_ROLE in roles or AGENCY_ADMIN_ROLE in roles:
        return True
    return lead.assigned_agent_id == user_id


def assert_lead_writable(db: Session, lead: Lead) -> None:
    submission_match = _lead_property_submission(db, lead)
    submission = submission_match[0] if submission_match else None
    if submission and submission.status == DEAL_CLOSED_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Leads for deal closed properties are read-only")


def _lead_query_for_context(db: Session, *, user_id: UUID, roles: tuple[str, ...], agency_id: UUID | None):
    stmt = select(Lead).order_by(Lead.updated_at.desc(), Lead.created_at.desc())
    if SUPER_ADMIN_ROLE in roles:
        return stmt
    if AGENCY_ADMIN_ROLE in roles and agency_id:
        mapped_user_ids = agency_user_ids(db, agency_id=agency_id)
        legacy_user_ids = select(User.id).where(User.agency_id == agency_id)
        property_ids = (
            select(PropertyListingSubmission.property_id)
            .join(User, User.id == PropertyListingSubmission.submitted_by)
            .where(
                or_(
                    PropertyListingSubmission.agency_id == agency_id,
                    PropertyListingSubmission.agency_id.is_(None) & (User.agency_id == agency_id),
                ),
                PropertyListingSubmission.property_id.is_not(None),
            )
        )
        return stmt.where(
            or_(
                Lead.assigned_agent_id.in_(mapped_user_ids),
                Lead.assigned_agent_id.in_(legacy_user_ids),
                Lead.created_by_agent_id.in_(mapped_user_ids),
                Lead.created_by_agent_id.in_(legacy_user_ids),
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
    submission_agency_id = _submission_agency_id(submission, submitter)
    notify_users.extend(_agency_admins(db, submission_agency_id))
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
            purpose=EmailPurpose.GENERAL,
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
        "close_reason": lead.close_reason,
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


def list_owner_enquiries(
    db: Session,
    *,
    owner_id: UUID,
    page: int,
    page_size: int,
    search: str | None = None,
    status: str | None = None,
    source: str | None = None,
    inquiry_type: str | None = None,
    assigned_agent_id: UUID | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """List only enquiries created by the authenticated owner."""
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = select(Lead).where(Lead.user_id == owner_id)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Lead.lead_number.ilike(pattern),
                Lead.external_owner_name.ilike(pattern),
                Lead.external_owner_email.ilike(pattern),
                Lead.external_owner_phone.ilike(pattern),
                Lead.external_property_name.ilike(pattern),
                Lead.inquiry_type.ilike(pattern),
                Lead.message.ilike(pattern),
            )
        )
    if status and status.strip() and status.strip().lower() != "all":
        stmt = stmt.where(Lead.status == status.strip().upper())
    if source and source.strip() and source.strip().lower() != "all":
        stmt = stmt.where(Lead.source == source.strip().upper())
    if inquiry_type and inquiry_type.strip() and inquiry_type.strip().lower() != "all":
        stmt = stmt.where(Lead.inquiry_type == inquiry_type.strip())
    if assigned_agent_id is not None:
        stmt = stmt.where(Lead.assigned_agent_id == assigned_agent_id)

    sort_columns = {
        "created_at": Lead.created_at,
        "createdAt": Lead.created_at,
        "updated_at": Lead.updated_at,
        "updatedAt": Lead.updated_at,
        "last_activity_at": Lead.last_activity_at,
        "lastActivityAt": Lead.last_activity_at,
        "lead_number": Lead.lead_number,
        "leadNumber": Lead.lead_number,
        "status": Lead.status,
        "source": Lead.source,
    }
    sort_column = sort_columns.get(sort_by, Lead.updated_at)
    direction = sort_order.strip().lower()
    stmt = stmt.order_by(sort_column.asc() if direction == "asc" else sort_column.desc().nullslast())

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
    assert_lead_writable(db, lead)
    if AGENCY_ADMIN_ROLE not in actor_roles and SUPER_ADMIN_ROLE not in actor_roles:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin or Super Admin can assign leads")
    if agent_id:
        agent = db.get(User, agent_id)
        if not agent or not agent.is_active or not user_has_role(db, agent.id, AGENT_ROLE):
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agent not found")
        has_mapping = bool(
            actor_agency_id
            and user_has_active_agency_mapping(
                db,
                user_id=agent.id,
                agency_id=actor_agency_id,
                relationship_type=REL_AGENT,
            )
        )
        has_legacy_agency = bool(actor_agency_id and agent.agency_id == actor_agency_id)
        if AGENCY_ADMIN_ROLE in actor_roles and actor_agency_id and not (has_mapping or has_legacy_agency):
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


def serialize_lead_close_request(request: LeadCloseRequest) -> dict[str, Any]:
    return {
        "id": str(request.id),
        "lead_id": str(request.lead_id),
        "requested_by": str(request.requested_by),
        "status": request.status,
        "reason": request.reason,
        "reviewed_by": str(request.reviewed_by) if request.reviewed_by else None,
        "review_reason": request.review_reason,
        "requested_at": iso(request.requested_at),
        "reviewed_at": iso(request.reviewed_at),
        "canceled_by": str(request.canceled_by) if request.canceled_by else None,
        "canceled_at": iso(request.canceled_at),
        "created_at": iso(request.created_at),
        "updated_at": iso(request.updated_at),
    }


def get_lead_close_request_or_404(db: Session, request_id: UUID) -> LeadCloseRequest:
    request = db.get(LeadCloseRequest, request_id)
    if not request:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Lead close request not found")
    return request


def list_lead_close_requests(db: Session, *, lead_id: UUID) -> list[dict[str, Any]]:
    requests = db.execute(
        select(LeadCloseRequest)
        .where(LeadCloseRequest.lead_id == lead_id)
        .order_by(LeadCloseRequest.requested_at.desc())
    ).scalars().all()
    return [serialize_lead_close_request(request) for request in requests]


def _pending_lead_close_request_stmt(lead_id: UUID, *, lock: bool = False):
    stmt = (
        select(LeadCloseRequest)
        .where(
            LeadCloseRequest.lead_id == lead_id,
            LeadCloseRequest.status == CLOSE_REQUEST_PENDING,
        )
        .order_by(LeadCloseRequest.requested_at.desc())
    )
    if lock:
        stmt = stmt.with_for_update()
    return stmt


def find_pending_lead_close_request(
    db: Session,
    *,
    lead_id: UUID,
    lock: bool = False,
) -> LeadCloseRequest | None:
    return db.execute(_pending_lead_close_request_stmt(lead_id, lock=lock)).scalar_one_or_none()


def get_pending_lead_close_request(db: Session, *, lead_id: UUID, lock: bool = False) -> LeadCloseRequest:
    request = find_pending_lead_close_request(db, lead_id=lead_id, lock=lock)
    if not request:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="No pending close request exists for this lead")
    return request


def _backfill_pending_lead_close_request(
    db: Session,
    *,
    lead: Lead,
    reason: str | None = None,
) -> LeadCloseRequest:
    requested_by = lead.assigned_agent_id or lead.created_by_agent_id
    if requested_by is None:
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="No pending close request exists for this lead",
        )

    now = utc_now()
    if lead.status != "REQUEST_FOR_CLOSE":
        previous_status = lead.status
        lead.status = "REQUEST_FOR_CLOSE"
        lead.request_close_at = lead.request_close_at or now
        lead.last_activity_at = now
        record_status_history(
            db,
            lead=lead,
            from_status=previous_status,
            to_status="REQUEST_FOR_CLOSE",
            actor_user_id=requested_by,
            actor_role=AGENT_ROLE,
            reason=reason,
        )

    request = LeadCloseRequest(
        id=uuid4(),
        lead_id=lead.id,
        requested_by=requested_by,
        status=CLOSE_REQUEST_PENDING,
        reason=reason,
        requested_at=lead.request_close_at or now,
        created_at=now,
        updated_at=now,
    )
    db.add(request)
    db.flush()
    return request


def approve_lead_close(
    db: Session,
    *,
    lead: Lead,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    reason: str | None = None,
) -> LeadCloseRequest:
    lead = get_lead_for_update_or_404(db, lead.id)
    assert_lead_writable(db, lead)
    if lead.status == "CLOSED":
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Lead is already closed")

    pending = find_pending_lead_close_request(db, lead_id=lead.id, lock=True)
    if pending is None and (
        lead.status == "REQUEST_FOR_CLOSE" or lead.request_close_at is not None
    ):
        pending = _backfill_pending_lead_close_request(db, lead=lead, reason=reason)
    if pending is None:
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="No pending close request exists for this lead",
        )

    return review_lead_close_request(
        db,
        request=pending,
        lead=lead,
        approved=True,
        actor_user_id=actor_user_id,
        actor_roles=actor_roles,
        actor_agency_id=actor_agency_id,
        reason=reason,
    )


def create_lead_close_request(
    db: Session,
    *,
    lead: Lead,
    requested_by: UUID,
    actor_roles: tuple[str, ...],
    reason: str | None = None,
) -> LeadCloseRequest:
    lead = get_lead_for_update_or_404(db, lead.id)
    assert_lead_writable(db, lead)
    assert_assigned_agent_can_request_close(lead, user_id=requested_by, roles=actor_roles)
    if lead.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="Lead must be IN_PROGRESS before closure can be requested",
        )

    pending = db.execute(
        select(LeadCloseRequest).where(
            LeadCloseRequest.lead_id == lead.id,
            LeadCloseRequest.status == CLOSE_REQUEST_PENDING,
        )
    ).scalar_one_or_none()
    if pending:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="A pending close request already exists")

    now = utc_now()
    request = LeadCloseRequest(
        id=uuid4(),
        lead_id=lead.id,
        requested_by=requested_by,
        status=CLOSE_REQUEST_PENDING,
        reason=reason,
        requested_at=now,
        created_at=now,
        updated_at=now,
    )
    previous_status = lead.status
    lead.status = "REQUEST_FOR_CLOSE"
    lead.request_close_at = now
    lead.last_activity_at = now
    db.add(request)
    record_status_history(
        db,
        lead=lead,
        from_status=previous_status,
        to_status="REQUEST_FOR_CLOSE",
        actor_user_id=requested_by,
        actor_role=AGENT_ROLE,
        reason=reason,
    )
    record_activity(
        db,
        activity_type="lead_close_requested",
        message=f"Close requested for lead {lead.lead_number}",
        user_id=requested_by,
        property_id=lead.property_id,
    )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="A pending close request already exists",
        ) from exc
    return request


def review_lead_close_request(
    db: Session,
    *,
    request: LeadCloseRequest,
    lead: Lead,
    approved: bool,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    reason: str | None = None,
) -> LeadCloseRequest:
    lead = get_lead_for_update_or_404(db, lead.id)
    assert_admin_can_review_close(
        db,
        lead,
        actor_roles=actor_roles,
        actor_agency_id=actor_agency_id,
    )
    request = db.execute(
        select(LeadCloseRequest)
        .where(LeadCloseRequest.id == request.id, LeadCloseRequest.lead_id == lead.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="No pending close request exists for this lead")
    if request.status != CLOSE_REQUEST_PENDING:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="Lead close request has already been resolved")
    if lead.status != "REQUEST_FOR_CLOSE":
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="Lead is not awaiting close review",
        )

    now = utc_now()
    request.status = CLOSE_REQUEST_APPROVED if approved else CLOSE_REQUEST_REJECTED
    request.reviewed_by = actor_user_id
    request.review_reason = reason
    request.reviewed_at = now
    request.updated_at = now

    if approved:
        update_lead_status(
            db,
            lead=lead,
            status="CLOSED",
            actor_user_id=actor_user_id,
            actor_roles=actor_roles,
            reason=reason or request.reason,
            allow_close=True,
        )
        lead.close_reason = reason or request.reason
    else:
        previous_status = lead.status
        lead.status = "IN_PROGRESS"
        lead.request_close_at = None
        lead.last_activity_at = now
        record_status_history(
            db,
            lead=lead,
            from_status=previous_status,
            to_status="IN_PROGRESS",
            actor_user_id=actor_user_id,
            actor_role=primary_role(actor_roles),
            reason=reason,
        )

    record_activity(
        db,
        activity_type="lead_close_approved" if approved else "lead_close_rejected",
        message=f"Close request for lead {lead.lead_number} {'approved' if approved else 'rejected'}",
        user_id=actor_user_id,
        property_id=lead.property_id,
    )
    return request


def cancel_lead_close_request(
    db: Session,
    *,
    request: LeadCloseRequest,
    lead: Lead,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    reason: str | None = None,
) -> LeadCloseRequest:
    lead = get_lead_for_update_or_404(db, lead.id)
    request = db.execute(
        select(LeadCloseRequest)
        .where(LeadCloseRequest.id == request.id, LeadCloseRequest.lead_id == lead.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="No pending close request exists for this lead")
    if request.status != CLOSE_REQUEST_PENDING:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="Lead close request has already been resolved")
    is_requester = request.requested_by == actor_user_id and set(actor_roles) == {AGENT_ROLE}
    is_admin = SUPER_ADMIN_ROLE in actor_roles or AGENCY_ADMIN_ROLE in actor_roles
    if not is_requester and not is_admin:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only the requester or Agency Admin can cancel this close request")
    if is_admin:
        assert_admin_can_review_close(
            db,
            lead,
            actor_roles=actor_roles,
            actor_agency_id=actor_agency_id,
        )
    if lead.status != "REQUEST_FOR_CLOSE":
        raise HTTPException(status_code=STATUS_CONFLICT, detail="Lead is not awaiting close review")

    now = utc_now()
    request.status = CLOSE_REQUEST_CANCELED
    request.canceled_by = actor_user_id
    request.canceled_at = now
    request.review_reason = reason
    request.updated_at = now
    previous_status = lead.status
    lead.status = "IN_PROGRESS"
    lead.request_close_at = None
    lead.last_activity_at = now
    record_status_history(
        db,
        lead=lead,
        from_status=previous_status,
        to_status="IN_PROGRESS",
        actor_user_id=actor_user_id,
        actor_role=primary_role(actor_roles),
        reason=reason,
    )
    record_activity(
        db,
        activity_type="lead_close_canceled",
        message=f"Close request for lead {lead.lead_number} canceled",
        user_id=actor_user_id,
        property_id=lead.property_id,
    )
    return request


def update_lead_status(
    db: Session,
    *,
    lead: Lead,
    status: str,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    reason: str | None = None,
    allow_close: bool = False,
) -> Lead:
    assert_lead_writable(db, lead)
    if status not in LEAD_STATUSES:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid lead status")
    if lead.status == "CLOSED":
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Closed leads cannot be changed")
    if status == "REQUEST_FOR_CLOSE":
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="Use the close request workflow instead of changing the lead status",
        )
    if status == "CLOSED" and not allow_close:
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="Approve a pending close request to close the lead",
        )
    if status == "CLOSED" and AGENCY_ADMIN_ROLE not in actor_roles and SUPER_ADMIN_ROLE not in actor_roles:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin can close a lead")
    previous_status = lead.status
    lead.status = status
    lead.last_activity_at = utc_now()
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
    assert_lead_writable(db, lead)
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


def serialize_lead_note(note: LeadNote) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "lead_id": str(note.lead_id),
        "author_user_id": str(note.author_user_id) if note.author_user_id else None,
        "note": note.note,
        "created_at": iso(note.created_at),
        "updated_at": iso(note.updated_at),
    }


def list_lead_notes(
    db: Session,
    *,
    lead: Lead,
    user_id: UUID,
    roles: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not can_view_lead_internal_notes(lead, user_id=user_id, roles=roles):
        return []
    notes = db.execute(
        select(LeadNote)
        .where(LeadNote.lead_id == lead.id)
        .order_by(LeadNote.created_at.asc())
    ).scalars().all()
    return [serialize_lead_note(note) for note in notes]


def serialize_lead_status_history(entry: LeadStatusHistory) -> dict[str, Any]:
    from_label = entry.from_status or "none"
    return {
        "id": str(entry.id),
        "kind": "status_change",
        "activity_type": "status_change",
        "message": f"Status changed from {from_label} to {entry.to_status}",
        "user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
        "from_status": entry.from_status,
        "to_status": entry.to_status,
        "reason": entry.reason,
        "actor_role": entry.actor_role,
        "created_at": iso(entry.changed_at),
    }


def serialize_lead_audit_activity(entry: ActivityLog) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "kind": "audit",
        "activity_type": entry.activity_type,
        "message": entry.message,
        "user_id": str(entry.user_id) if entry.user_id else None,
        "tone": entry.tone,
        "created_at": iso(entry.created_at),
    }


def list_lead_activity(db: Session, *, lead: Lead) -> list[dict[str, Any]]:
    status_history = db.execute(
        select(LeadStatusHistory)
        .where(LeadStatusHistory.lead_id == lead.id)
        .order_by(LeadStatusHistory.changed_at.asc())
    ).scalars().all()

    audit_filters = [
        ActivityLog.activity_type == "lead_assigned",
        ActivityLog.message.ilike(f"%{lead.lead_number}%"),
    ]
    if lead.property_id:
        audit_filters.insert(0, ActivityLog.property_id == lead.property_id)

    assignment_activity = db.execute(
        select(ActivityLog).where(*audit_filters).order_by(ActivityLog.created_at.asc())
    ).scalars().all()

    items = [serialize_lead_status_history(entry) for entry in status_history]
    items.extend(serialize_lead_audit_activity(entry) for entry in assignment_activity)
    items.sort(key=lambda item: item["created_at"] or "")
    return items


def serialize_lead_message(message: LeadMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "lead_id": str(message.lead_id),
        "sender_user_id": str(message.sender_user_id) if message.sender_user_id else None,
        "recipient_user_id": str(message.recipient_user_id) if message.recipient_user_id else None,
        "message": message.message,
        "channel": message.channel,
        "delivery_state": message.delivery_state,
        "created_at": iso(message.created_at),
    }


def list_lead_messages(db: Session, *, lead_id: UUID) -> list[dict[str, Any]]:
    messages = db.execute(
        select(LeadMessage)
        .where(LeadMessage.lead_id == lead_id)
        .order_by(LeadMessage.created_at.asc())
    ).scalars().all()
    return [serialize_lead_message(message) for message in messages]


def add_lead_message(
    db: Session,
    *,
    lead: Lead,
    sender_user_id: UUID,
    recipient_user_id: UUID | None,
    message: str,
    channel: str,
) -> LeadMessage:
    assert_lead_writable(db, lead)
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
            send_email_notification(
                to_email=recipient.email,
                subject="Lead message",
                body=message,
                purpose=EmailPurpose.GENERAL,
            )
        if recipient and channel == "SMS" and recipient.phone_number:
            send_sms_notification(to_phone=recipient.phone_number, body=message)
    return record
