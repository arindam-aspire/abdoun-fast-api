from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.live_schema import AgencyMaster, PropertyListingSubmission, User
from app.services.audit import record_activity
from app.services.notifications import create_in_app_notification
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_NOT_FOUND


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
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
    status: str = "draft",
) -> PropertyListingSubmission:
    submitted_at = utc_now() if status == "submitted" else None
    submission = PropertyListingSubmission(
        id=uuid4(),
        submitted_by=user_id,
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
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
) -> PropertyListingSubmission:
    if submission.status not in {"draft", "rejected", "in_progress"}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only draft or rejected submissions can be edited")
    submission.payload = payload
    submission.current_step = current_step
    submission.last_completed_step = last_completed_step
    submission.step_completion = compute_step_completion(payload)
    submission.status = "draft"
    return submission


def submit_submission(submission: PropertyListingSubmission) -> PropertyListingSubmission:
    if submission.status in {"approved"}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Approved submissions cannot be resubmitted")
    submission.status = "submitted"
    submission.submitted_at = utc_now()
    submission.step_completion = compute_step_completion(submission.payload or {})
    return submission


def soft_delete_submission(submission: PropertyListingSubmission, *, deleted_by: UUID) -> None:
    submission.deleted_at = utc_now()
    submission.deleted_by = deleted_by
    submission.delete_reason = "Deleted by user"


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
        "agency": None,
        "submitted_by": str(submitter.id) if submitter else str(submission.submitted_by),
        "agent_user_id": workflow.get("assigned_agent_id"),
    }


def serialize_admin_submission_item(submission: PropertyListingSubmission, submitter: User | None = None) -> dict:
    payload = submission.payload or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    return {
        "submission_id": str(submission.id),
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
        stmt = stmt.where(User.agency_id == agency_id)
    stmt = stmt.order_by(PropertyListingSubmission.updated_at.desc())
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, _pagination(total, page, page_size)


def assign_agent_to_property(db: Session, *, property_id: UUID, agent_id: UUID | None) -> PropertyListingSubmission:
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
    payload = dict(submission.payload or {})
    workflow = _payload_workflow(payload)
    workflow["assigned_agent_id"] = str(agent_id) if agent_id else None
    submission.payload = payload
    return submission
