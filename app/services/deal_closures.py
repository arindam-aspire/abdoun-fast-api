from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deal_closure import PropertyDealClosure
from app.models.live_schema import Lead, PropertyListingSubmission, User
from app.schemas.deal_closures import DealClosureCreate
from app.services.audit import record_activity
from app.services.notifications import create_in_app_notification
from app.services.public_properties import get_public_submission_or_404, pagination_meta, serialize_property_listing
from app.services.property_submissions import _payload_workflow
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_FORBIDDEN, STATUS_NOT_FOUND


PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def get_deal_closure_or_404(db: Session, closure_id: UUID) -> PropertyDealClosure:
    closure = db.get(PropertyDealClosure, closure_id)
    if not closure:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Deal closure request not found")
    return closure


def _submission_for_property(db: Session, property_id: UUID) -> tuple[PropertyListingSubmission, User | None] | None:
    try:
        return get_public_submission_or_404(db, property_id)
    except HTTPException:
        return db.execute(
            select(PropertyListingSubmission, User)
            .join(User, User.id == PropertyListingSubmission.submitted_by)
            .where(
                PropertyListingSubmission.property_id == property_id,
                PropertyListingSubmission.deleted_at.is_(None),
            )
            .order_by(PropertyListingSubmission.updated_at.desc())
        ).first()


def _agency_id_for_property(db: Session, property_id: UUID) -> UUID | None:
    match = _submission_for_property(db, property_id)
    if match and match[0].agency_id:
        return match[0].agency_id
    submitter = match[1] if match else None
    return submitter.agency_id if submitter else None


def _can_request_closure(
    db: Session,
    *,
    property_id: UUID,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    match = _submission_for_property(db, property_id)
    if not match:
        return False
    submission, submitter = match
    role_names = {role.lower() for role in roles}
    if submission.submitted_by == user_id:
        return True
    workflow = (submission.payload or {}).get("_workflow") or {}
    if workflow.get("assigned_agent_id") == str(user_id):
        return True
    property_agency_id = submission.agency_id or (submitter.agency_id if submitter else None)
    if "admin" in role_names and agency_id and property_agency_id == agency_id:
        return True
    return False


def _assert_agency_admin_can_review(
    db: Session,
    *,
    closure: PropertyDealClosure,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    role_names = {role.lower() for role in roles}
    if "admin" not in role_names:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin can review deal closure requests")
    if closure.agency_id and agency_id != closure.agency_id:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Deal closure request is outside the agency")


def _assert_can_view(
    closure: PropertyDealClosure,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    role_names = {role.lower() for role in roles}
    if "super_admin" in role_names:
        return
    if closure.requested_by == user_id:
        return
    if "admin" in role_names and closure.agency_id and agency_id == closure.agency_id:
        return
    raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def _mark_submission_deal_status(db: Session, property_id: UUID, *, status: str, closure_id: UUID) -> None:
    submissions = db.execute(
        select(PropertyListingSubmission).where(
            PropertyListingSubmission.property_id == property_id,
            PropertyListingSubmission.deleted_at.is_(None),
        )
    ).scalars().all()
    for submission in submissions:
        payload = dict(submission.payload or {})
        workflow = _payload_workflow(payload)
        workflow["deal_closure_status"] = status
        workflow["deal_closure_id"] = str(closure_id)
        submission.payload = payload


def create_deal_closure(
    db: Session,
    *,
    payload: DealClosureCreate,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> PropertyDealClosure:
    submission, _ = get_public_submission_or_404(db, payload.property_hash)
    property_id = submission.property_id or submission.id
    if not _can_request_closure(db, property_id=property_id, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")
    existing = db.execute(
        select(PropertyDealClosure).where(
            PropertyDealClosure.property_id == property_id,
            PropertyDealClosure.status.in_([PENDING, APPROVED]),
        )
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Deal closure already exists for this property")

    closure = PropertyDealClosure(
        id=uuid4(),
        property_id=property_id,
        lead_id=payload.lead_id,
        agency_id=_agency_id_for_property(db, property_id),
        requested_by=user_id,
        status=PENDING,
        reason=payload.reason,
        requested_at=utc_now(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(closure)
    _mark_submission_deal_status(db, property_id, status="deal_closure_requested", closure_id=closure.id)
    record_activity(
        db,
        activity_type="deal_closure_requested",
        message=f"Deal closure requested for property {property_id}",
        user_id=user_id,
        property_id=property_id,
    )
    return closure


def review_deal_closure(
    db: Session,
    *,
    closure: PropertyDealClosure,
    action: str,
    reason: str | None,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> PropertyDealClosure:
    _assert_agency_admin_can_review(
        db,
        closure=closure,
        user_id=actor_user_id,
        roles=actor_roles,
        agency_id=actor_agency_id,
    )
    if closure.status != PENDING:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Deal closure request is already reviewed")
    if action == "approve":
        closure.status = APPROVED
        _mark_submission_deal_status(db, closure.property_id, status="deal_closed", closure_id=closure.id)
        if closure.lead_id:
            lead = db.get(Lead, closure.lead_id)
            if lead and lead.status != "CLOSED":
                lead.status = "CLOSED"
                lead.closed_at = utc_now()
                lead.closed_by_admin_id = actor_user_id
    elif action == "reject":
        closure.status = REJECTED
        _mark_submission_deal_status(db, closure.property_id, status="active", closure_id=closure.id)
    else:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid review action")
    closure.review_reason = reason
    closure.reviewed_by = actor_user_id
    closure.reviewed_at = utc_now()
    closure.updated_at = utc_now()
    record_activity(
        db,
        activity_type=f"deal_closure_{closure.status.lower()}",
        message=f"Deal closure {closure.status.lower()} for property {closure.property_id}",
        user_id=actor_user_id,
        property_id=closure.property_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=closure.requested_by,
        actor_user_id=actor_user_id,
        type_key=f"deal_closure_{closure.status.lower()}",
        title="Deal closure reviewed",
        message=f"Your deal closure request was {closure.status.lower()}.",
        data={"deal_closure_id": str(closure.id), "property_id": str(closure.property_id)},
    )
    return closure


def serialize_deal_closure(db: Session, closure: PropertyDealClosure) -> dict[str, Any]:
    match = _submission_for_property(db, closure.property_id)
    property_payload = serialize_property_listing(db, match[0], submitter=match[1]) if match else None
    return {
        "id": str(closure.id),
        "property_id": str(closure.property_id),
        "property_hash": property_payload.get("property_hash") if property_payload else None,
        "property": property_payload,
        "lead_id": str(closure.lead_id) if closure.lead_id else None,
        "agency_id": str(closure.agency_id) if closure.agency_id else None,
        "requested_by": str(closure.requested_by),
        "status": closure.status,
        "reason": closure.reason,
        "review_reason": closure.review_reason,
        "reviewed_by": str(closure.reviewed_by) if closure.reviewed_by else None,
        "requested_at": iso(closure.requested_at),
        "reviewed_at": iso(closure.reviewed_at),
        "created_at": iso(closure.created_at),
        "updated_at": iso(closure.updated_at),
    }


def list_deal_closures(
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
    stmt = select(PropertyDealClosure).order_by(PropertyDealClosure.created_at.desc())
    role_names = {role.lower() for role in roles}
    if "super_admin" not in role_names:
        if "admin" in role_names and agency_id:
            stmt = stmt.where(PropertyDealClosure.agency_id == agency_id)
        else:
            stmt = stmt.where(PropertyDealClosure.requested_by == user_id)
    if status:
        stmt = stmt.where(PropertyDealClosure.status == status.upper())
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    closures = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return [serialize_deal_closure(db, closure) for closure in closures], pagination_meta(total, page, page_size)
