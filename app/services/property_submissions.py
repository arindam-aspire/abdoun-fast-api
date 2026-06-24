from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.live_schema import AgencyMaster, PropertyListingSubmission, User
from app.services.audit import record_activity
from app.services.notifications import create_in_app_notification, send_email_notification, send_sms_notification
from app.services.user_agencies import (
    REL_AGENT,
    REL_PROPERTY_OWNER,
    active_mappings,
    agency_users_with_role,
    ensure_user_agency_mapping,
    user_has_active_agency_mapping,
)
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_FORBIDDEN, STATUS_NOT_FOUND


SUBMISSION_SECTIONS = (
    "basic_information",
    "location",
    "owner_information",
    "property_details",
    "pricing",
    "amenities",
    "media_documents",
    "review_submit",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _title(payload: dict[str, Any]) -> str | None:
    basic = payload.get("basic_information") or {}
    return basic.get("title")


def _payload_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = payload.get("_workflow")
    if not isinstance(workflow, dict):
        workflow = {}
        payload["_workflow"] = workflow
    return workflow


def compute_step_completion(payload: dict[str, Any]) -> dict[str, bool]:
    return {section: bool(payload.get(section)) for section in SUBMISSION_SECTIONS}


def serialize_submission(submission: PropertyListingSubmission) -> dict:
    payload = submission.payload or {}
    return {
        "submission_id": str(submission.id),
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
        "status": submission.status,
        "current_step": submission.current_step,
        "last_completed_step": submission.last_completed_step,
        "step_completion": submission.step_completion or compute_step_completion(payload),
        "payload": payload,
        "reviewed_by": str(submission.reviewed_by) if submission.reviewed_by else None,
        "reviewed_at": _iso(submission.reviewed_at),
        "review_reason": submission.review_reason,
    }


def _pagination(total: int, page: int, page_size: int) -> dict:
    total_pages = math.ceil(total / page_size) if total else 1
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }


def create_submission(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID | None,
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
    status: str = "draft",
) -> PropertyListingSubmission:
    submitted_at = utc_now() if status == "submitted" else None
    submission = PropertyListingSubmission(
        id=uuid4(),
        submitted_by=user_id,
        agency_id=agency_id,
        status=status,
        current_step=current_step,
        last_completed_step=last_completed_step,
        payload=payload,
        step_completion=compute_step_completion(payload),
        terms_accepted=bool((payload.get("review_submit") or {}).get("terms_accepted")),
        privacy_accepted=bool((payload.get("review_submit") or {}).get("privacy_accepted")),
        public_display_authorized=bool((payload.get("review_submit") or {}).get("public_display_authorized")),
        fees_acknowledged=bool((payload.get("review_submit") or {}).get("fees_acknowledged")),
        submitted_at=submitted_at,
    )
    db.add(submission)
    return submission


def get_submission_or_404(db: Session, submission_id: UUID) -> PropertyListingSubmission:
    submission = db.get(PropertyListingSubmission, submission_id)
    if not submission or submission.deleted_at is not None:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property submission not found")
    return submission


def update_submission(
    submission: PropertyListingSubmission,
    *,
    agency_id: UUID | None,
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
) -> PropertyListingSubmission:
    if submission.status not in {"draft", "rejected", "in_progress"}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only draft or rejected submissions can be edited")
    submission.payload = payload
    if agency_id is not None:
        submission.agency_id = agency_id
    submission.current_step = current_step
    submission.last_completed_step = last_completed_step
    submission.step_completion = compute_step_completion(payload)
    submission.status = "draft"
    return submission


def can_edit_approved_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    role_names = {role.lower() for role in roles}
    if submission.submitted_by == user_id:
        return True

    workflow = (submission.payload or {}).get("_workflow") or {}
    if workflow.get("assigned_agent_id") == str(user_id):
        return True

    if "admin" in role_names and agency_id:
        return _submitter_agency_id(db, submission) == agency_id

    return False


def _role_names(roles: tuple[str, ...]) -> set[str]:
    return {role.lower() for role in roles}


def _assigned_agent_id(submission: PropertyListingSubmission) -> str | None:
    workflow = (submission.payload or {}).get("_workflow") or {}
    return workflow.get("assigned_agent_id")


def _submitter_agency_id(db: Session, submission: PropertyListingSubmission) -> UUID | None:
    if submission.agency_id:
        return submission.agency_id
    submitter = db.get(User, submission.submitted_by)
    return submitter.agency_id if submitter else None


def can_view_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    role_names = _role_names(roles)
    if "super_admin" in role_names:
        return True
    if submission.submitted_by == user_id:
        return True
    if _assigned_agent_id(submission) == str(user_id):
        return True
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return True
    return False


def can_edit_working_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    if submission.submitted_by == user_id:
        return True
    if _assigned_agent_id(submission) == str(user_id):
        return True
    if "admin" in _role_names(roles) and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return True
    return False


def assert_can_view_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    if not can_view_submission(db, submission, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def assert_can_edit_working_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    if not can_edit_working_submission(db, submission, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def assert_can_manage_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    role_names = _role_names(roles)
    if "super_admin" in role_names:
        return
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return
    raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def create_revision_from_approved(
    db: Session,
    *,
    source: PropertyListingSubmission,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
) -> PropertyListingSubmission:
    if source.status != "approved":
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only approved submissions can create revisions")
    if not can_edit_approved_submission(db, source, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Approved property cannot be edited by this user")

    revision_payload = dict(payload)
    workflow = _payload_workflow(revision_payload)
    workflow["revision_of_submission_id"] = str(source.id)
    workflow["revision_property_id"] = str(source.property_id or source.id)
    workflow["revision_status"] = "pending_reapproval"

    revision = PropertyListingSubmission(
        id=uuid4(),
        submitted_by=user_id,
        agency_id=_submitter_agency_id(db, source),
        property_id=source.property_id or source.id,
        status="submitted",
        current_step=current_step,
        last_completed_step=last_completed_step,
        payload=revision_payload,
        step_completion=compute_step_completion(revision_payload),
        terms_accepted=True,
        privacy_accepted=True,
        public_display_authorized=True,
        fees_acknowledged=True,
        submitted_at=utc_now(),
    )
    db.add(revision)
    record_activity(
        db,
        activity_type="property_revision_submitted",
        message=f"Revision submitted for approved property {revision.property_id}",
        user_id=user_id,
        property_id=revision.property_id,
    )
    return revision


def submit_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None = None,
) -> PropertyListingSubmission:
    if submission.status in {"approved"}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Approved submissions cannot be resubmitted")
    if agency_id is not None and submission.status in {"draft", "rejected", "in_progress"}:
        submission.agency_id = agency_id
    resolve_listing_agency_or_400(db, submission.agency_id)
    assert_owner_agency_rule(db, user_id=user_id, agency_id=submission.agency_id, roles=roles)
    record_owner_agency_mapping_for_submission(db, user_id=user_id, agency_id=submission.agency_id, roles=roles)
    submission.status = "submitted"
    submission.submitted_at = utc_now()
    submission.step_completion = compute_step_completion(submission.payload or {})
    notify_agency_admins_for_submission(db, submission=submission, actor_user_id=user_id)
    return submission


def soft_delete_submission(submission: PropertyListingSubmission, *, deleted_by: UUID) -> None:
    submission.deleted_at = utc_now()
    submission.deleted_by = deleted_by
    submission.delete_reason = "Deleted by user"


def resolve_listing_agency_or_400(db: Session, agency_id: UUID | None) -> AgencyMaster:
    if agency_id is None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency is required before submitting a property")
    agency = db.get(AgencyMaster, agency_id)
    if not agency or not agency.is_active or not agency.is_verified:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Selected agency is not available for property submission")
    return agency


def assert_owner_agency_rule(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID,
    roles: tuple[str, ...],
) -> None:
    role_names = _role_names(roles)
    if "owner" not in role_names and "registered_user" not in role_names:
        return
    settings = get_settings()
    mappings = active_mappings(db, user_id=user_id, relationship_type=REL_PROPERTY_OWNER)
    if mappings and not settings.allow_owner_multiple_agencies and all(mapping.agency_id != agency_id for mapping in mappings):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Owner is already linked to another agency")


def record_owner_agency_mapping_for_submission(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID,
    roles: tuple[str, ...],
) -> None:
    role_names = _role_names(roles)
    if "owner" not in role_names and "registered_user" not in role_names:
        return
    created = not user_has_active_agency_mapping(
        db,
        user_id=user_id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
    )
    ensure_user_agency_mapping(
        db,
        user_id=user_id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
        actor_user_id=user_id,
    )
    if created and get_settings().allow_owner_multiple_agencies:
        record_activity(
            db,
            activity_type="owner_agency_mapping_created",
            message=f"Owner {user_id} linked to agency {agency_id}",
            user_id=user_id,
        )


def notify_agency_admins_for_submission(db: Session, *, submission: PropertyListingSubmission, actor_user_id: UUID) -> None:
    if not submission.agency_id:
        return
    recipients = agency_users_with_role(db, agency_id=submission.agency_id, role_name="admin")
    payload = submission.payload or {}
    title = ((payload.get("basic_information") or {}).get("title")) or "property listing"
    for recipient in recipients:
        create_in_app_notification(
            db,
            recipient_user_id=recipient.id,
            actor_user_id=actor_user_id,
            type_key="property_submission_created",
            title="New property submission",
            message=f"New property submission received for {title}.",
            data={"submission_id": str(submission.id), "agency_id": str(submission.agency_id)},
        )
        send_email_notification(
            to_email=recipient.email,
            subject="New property submission",
            body=f"New property submission received for {title}.",
        )
        if recipient.phone_number:
            send_sms_notification(
                to_phone=recipient.phone_number,
                body=f"New property submission received for {title}.",
            )


def review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    actor_id: UUID,
    action: str,
    reason: str | None = None,
) -> PropertyListingSubmission:
    if action == "approve":
        submission.status = "approved"
        submission.review_reason = None
        if not submission.property_id:
            submission.property_id = uuid4()
    elif action == "reject":
        if not reason:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Rejection reason is required")
        submission.status = "rejected"
        submission.review_reason = reason
    else:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid review action")

    submission.reviewed_by = actor_id
    submission.reviewed_at = utc_now()
    record_activity(
        db,
        activity_type=f"property_submission_{submission.status}",
        message=f"Property submission {submission.id} {submission.status}",
        user_id=actor_id,
        property_id=submission.property_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=submission.submitted_by,
        actor_user_id=actor_id,
        type_key=f"property_submission_{submission.status}",
        title="Property submission reviewed",
        message=f"Your property submission was {submission.status}.",
        data={"submission_id": str(submission.id), "property_id": str(submission.property_id) if submission.property_id else None},
    )
    return submission


def serialize_draft_list_item(submission: PropertyListingSubmission) -> dict:
    return {
        "submission_id": str(submission.id),
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
        "status": submission.status,
        "current_step": submission.current_step,
        "last_completed_step": submission.last_completed_step,
        "title": _title(submission.payload or {}),
        "updated_at": _iso(submission.updated_at),
        "can_edit": submission.status in {"draft", "rejected", "in_progress"},
        "can_delete": submission.status in {"draft", "rejected", "in_progress"},
    }


def stable_property_hash(property_id: UUID) -> int:
    return property_id.int % 2147483647


def serialize_agent_property_item(submission: PropertyListingSubmission, submitter: User | None = None) -> dict:
    payload = submission.payload or {}
    basic = payload.get("basic_information") or {}
    pricing = payload.get("pricing") or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    agency = None
    if submission.agency_id:
        agency = {"agency_id": str(submission.agency_id), "id": str(submission.agency_id)}
    return {
        "property_id": str(property_id),
        "property_hash": stable_property_hash(property_id),
        "title": basic.get("title") or "Untitled property",
        "listing_purpose": basic.get("listing_purpose") or "",
        "type_name": str(basic.get("type_id") or ""),
        "type_slug": str(basic.get("type_id") or ""),
        "category_name": str(basic.get("category_id") or ""),
        "category_slug": str(basic.get("category_id") or ""),
        "status_name": submission.status,
        "status_slug": submission.status,
        "price": str(pricing.get("price") or "0"),
        "currency": pricing.get("currency") or "JOD",
        "reference_number": (payload.get("property_details") or {}).get("reference_number") or str(property_id)[:8],
        "created_at": _iso(submission.created_at),
        "updated_at": _iso(submission.updated_at),
        "submission_id": str(submission.id),
        "submission_status": submission.status,
        "submission_submitted_at": _iso(submission.submitted_at),
        "submission_reviewed_at": _iso(submission.reviewed_at),
        "submission_review_reason": submission.review_reason,
        "submission_workflow_label": submission.status.replace("_", " ").title(),
        "can_edit_submission": submission.status in {"draft", "rejected", "in_progress"},
        "can_delete_submission": submission.status in {"draft", "rejected", "in_progress"},
        "agency": agency,
        "submitted_by": str(submitter.id) if submitter else str(submission.submitted_by),
        "agent_user_id": workflow.get("assigned_agent_id"),
    }


def serialize_admin_submission_item(submission: PropertyListingSubmission, submitter: User | None = None) -> dict:
    payload = submission.payload or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    return {
        "submission_id": str(submission.id),
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
        "submitted_by": str(submission.submitted_by),
        "submitted_by_name": submitter.full_name if submitter else "",
        "status": submission.status,
        "property_id": str(property_id),
        "agent_user_id": workflow.get("assigned_agent_id"),
        "has_assigned_agent": bool(workflow.get("assigned_agent_id")),
        "property_hash": stable_property_hash(property_id),
        "property_title": _title(payload) or "Untitled property",
        "property_reference_number": (payload.get("property_details") or {}).get("reference_number"),
        "current_step": submission.current_step,
        "submitted_at": _iso(submission.submitted_at) or _iso(submission.created_at),
        "reviewed_at": _iso(submission.reviewed_at),
    }


def list_submissions(
    db: Session,
    *,
    page: int,
    page_size: int,
    statuses: set[str] | None = None,
    submitted_by: UUID | None = None,
    agency_id: UUID | None = None,
) -> tuple[list[tuple[PropertyListingSubmission, User | None]], dict]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = (
        select(PropertyListingSubmission, User)
        .join(User, User.id == PropertyListingSubmission.submitted_by)
        .where(PropertyListingSubmission.deleted_at.is_(None))
    )
    if statuses:
        stmt = stmt.where(PropertyListingSubmission.status.in_(statuses))
    if submitted_by:
        stmt = stmt.where(PropertyListingSubmission.submitted_by == submitted_by)
    if agency_id:
        stmt = stmt.where(
            or_(
                PropertyListingSubmission.agency_id == agency_id,
                PropertyListingSubmission.agency_id.is_(None) & (User.agency_id == agency_id),
            )
        )
    stmt = stmt.order_by(PropertyListingSubmission.updated_at.desc())
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, _pagination(total, page, page_size)


def assign_agent_to_property(
    db: Session,
    *,
    property_id: UUID,
    agent_id: UUID | None,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> PropertyListingSubmission:
    submission = db.execute(
        select(PropertyListingSubmission).where(
            or_(
                PropertyListingSubmission.property_id == property_id,
                PropertyListingSubmission.id == property_id,
            ),
            PropertyListingSubmission.deleted_at.is_(None),
        )
    ).scalars().first()
    if not submission:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property submission not found")
    assert_can_manage_submission(db, submission, roles=actor_roles, agency_id=actor_agency_id)
    submission_agency_id = _submitter_agency_id(db, submission)
    if agent_id:
        agent = db.get(User, agent_id)
        if not agent:
            raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agent not found")
        has_mapping = bool(
            submission_agency_id
            and user_has_active_agency_mapping(
                db,
                user_id=agent.id,
                agency_id=submission_agency_id,
                relationship_type=REL_AGENT,
            )
        )
        has_legacy_agency = bool(submission_agency_id and agent.agency_id == submission_agency_id)
        if submission_agency_id and not has_mapping and not has_legacy_agency:
            raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent is outside the property agency")
    payload = dict(submission.payload or {})
    workflow = _payload_workflow(payload)
    workflow["assigned_agent_id"] = str(agent_id) if agent_id else None
    submission.payload = payload
    return submission
