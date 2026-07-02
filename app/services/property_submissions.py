from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

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

DRAFT_STATUSES = {"draft"}
PENDING_APPROVAL_STATUS = "pending-approval"
ACTIVE_STATUS = "active"
DEACTIVATED_STATUS = "deactivated"
DEAL_CLOSED_STATUS = "deal-closed"
DEAL_CLOSURE_REQUESTED_STATUS = "deal-closure-requested"
WORKING_STATUSES = {"draft", "rejected", "in_progress"}
WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT = "awaiting_agency_assignment"
WORKFLOW_STAGE_WITH_AGENT = "with_agent"
WORKFLOW_STAGE_AWAITING_AGENCY_REVIEW = "awaiting_agency_review"
WORKFLOW_STAGE_RETURNED_TO_OWNER = "returned_to_owner"
WORKFLOW_STAGE_RETURNED_TO_AGENT = "returned_to_agent"
WORKFLOW_STAGE_APPROVED = "approved"

CURRENT_ACTOR_OWNER = "owner"
CURRENT_ACTOR_ASSIGNED_AGENT = "assigned_agent"
CURRENT_ACTOR_AGENCY_ADMIN = "agency_admin"
CURRENT_ACTOR_NONE = None

SUBMISSION_ORIGIN_OWNER = "owner"
SUBMISSION_ORIGIN_AGENCY_ADMIN = "agency_admin"
SUBMISSION_ORIGIN_AGENT = "agent"
SUBMISSION_ORIGIN_SUPER_ADMIN = "super_admin"

ASSIGNMENT_READY_STAGES = {
    WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT,
    WORKFLOW_STAGE_AWAITING_AGENCY_REVIEW,
}
AGENCY_REVIEW_STAGES = {WORKFLOW_STAGE_AWAITING_AGENCY_REVIEW}
AGENT_EDIT_STAGES = {WORKFLOW_STAGE_WITH_AGENT, WORKFLOW_STAGE_RETURNED_TO_AGENT}
OWNER_EDIT_STAGES = {WORKFLOW_STAGE_RETURNED_TO_OWNER}
KNOWN_WORKFLOW_STAGES = {
    WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT,
    WORKFLOW_STAGE_WITH_AGENT,
    WORKFLOW_STAGE_AWAITING_AGENCY_REVIEW,
    WORKFLOW_STAGE_RETURNED_TO_OWNER,
    WORKFLOW_STAGE_RETURNED_TO_AGENT,
    WORKFLOW_STAGE_APPROVED,
}


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


def _role_names(roles: tuple[str, ...]) -> set[str]:
    return {role.lower() for role in roles}


def _workflow_from_submission(submission: PropertyListingSubmission) -> dict[str, Any]:
    workflow = (submission.payload or {}).get("_workflow") or {}
    return workflow if isinstance(workflow, dict) else {}


def _current_actor_for_workflow_stage(stage: str | None) -> str | None:
    if stage == WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT:
        return CURRENT_ACTOR_AGENCY_ADMIN
    if stage in AGENCY_REVIEW_STAGES:
        return CURRENT_ACTOR_AGENCY_ADMIN
    if stage in AGENT_EDIT_STAGES:
        return CURRENT_ACTOR_ASSIGNED_AGENT
    if stage in OWNER_EDIT_STAGES:
        return CURRENT_ACTOR_OWNER
    return CURRENT_ACTOR_NONE


def _workflow_stage_for_submission(submission: PropertyListingSubmission) -> str | None:
    workflow = _workflow_from_submission(submission)
    stage = workflow.get("workflow_stage")
    if isinstance(stage, str) and stage in KNOWN_WORKFLOW_STAGES:
        return stage
    if submission.status == PENDING_APPROVAL_STATUS:
        if workflow.get("assigned_agent_id"):
            return WORKFLOW_STAGE_WITH_AGENT
        return WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT
    if submission.status == "rejected":
        if workflow.get("assigned_agent_id"):
            return WORKFLOW_STAGE_RETURNED_TO_AGENT
        return WORKFLOW_STAGE_RETURNED_TO_OWNER
    if submission.status == ACTIVE_STATUS:
        return WORKFLOW_STAGE_APPROVED
    return None


def _submission_origin_for_roles(roles: tuple[str, ...]) -> str:
    role_names = _role_names(roles)
    if "agent" in role_names:
        return SUBMISSION_ORIGIN_AGENT
    if "super_admin" in role_names:
        return SUBMISSION_ORIGIN_SUPER_ADMIN
    if "admin" in role_names:
        return SUBMISSION_ORIGIN_AGENCY_ADMIN
    return SUBMISSION_ORIGIN_OWNER


def _set_submission_workflow(
    submission: PropertyListingSubmission,
    *,
    stage: str | None = None,
    origin: str | None = None,
    assigned_agent_id: UUID | str | None | object = ...,
    actor_user_id: UUID | None = None,
) -> dict[str, Any]:
    payload = dict(submission.payload or {})
    workflow = _payload_workflow(payload)
    if stage is not None:
        workflow["workflow_stage"] = stage
        workflow["current_actor"] = _current_actor_for_workflow_stage(stage)
    if origin is not None:
        workflow["submission_origin"] = origin
    if assigned_agent_id is not ...:
        workflow["assigned_agent_id"] = str(assigned_agent_id) if assigned_agent_id else None
    if actor_user_id is not None:
        workflow["last_actor_user_id"] = str(actor_user_id)
    workflow["last_transition_at"] = utc_now().isoformat()
    submission.payload = payload
    flag_modified(submission, "payload")
    return workflow


def _submission_workflow_summary(submission: PropertyListingSubmission) -> dict[str, Any]:
    workflow = _workflow_from_submission(submission)
    stage = _workflow_stage_for_submission(submission)
    return {
        "workflow_stage": stage,
        "current_actor": workflow.get("current_actor") or _current_actor_for_workflow_stage(stage),
        "submission_origin": workflow.get("submission_origin"),
        "assigned_agent_id": workflow.get("assigned_agent_id"),
    }


def _assigned_agent_uuid(submission: PropertyListingSubmission) -> UUID | None:
    value = _assigned_agent_id(submission)
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _assigned_agent_summary(db: Session, submission: PropertyListingSubmission) -> dict[str, str | None] | None:
    agent_id = _assigned_agent_uuid(submission)
    if not agent_id:
        return None
    agent = db.get(User, agent_id)
    if not agent:
        return {"id": str(agent_id), "name": None, "email": None, "phone": None}
    return {
        "id": str(agent.id),
        "name": agent.full_name,
        "email": agent.email,
        "phone": agent.phone_number,
    }


def compute_step_completion(payload: dict[str, Any]) -> dict[str, bool]:
    return {section: bool(payload.get(section)) for section in SUBMISSION_SECTIONS}


def serialize_submission(submission: PropertyListingSubmission) -> dict:
    payload = submission.payload or {}
    workflow_summary = _submission_workflow_summary(submission)
    return {
        "submission_id": str(submission.id),
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
        "status": submission.status,
        **workflow_summary,
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
    submitted_at = utc_now() if status == PENDING_APPROVAL_STATUS else None
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
    workflow_stage = _workflow_stage_for_submission(submission)
    is_editable_status = submission.status in {"draft", "rejected", "in_progress"} or (
        submission.status == PENDING_APPROVAL_STATUS and workflow_stage == WORKFLOW_STAGE_WITH_AGENT
    )
    if not is_editable_status:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="This property submission is not editable in its current workflow stage")
    next_payload = dict(payload)
    existing_workflow = _workflow_from_submission(submission)
    if existing_workflow:
        next_payload["_workflow"] = existing_workflow
    submission.payload = next_payload
    if agency_id is not None:
        submission.agency_id = agency_id
    submission.current_step = current_step
    submission.last_completed_step = last_completed_step
    submission.step_completion = compute_step_completion(next_payload)
    if submission.status in DRAFT_STATUSES:
        submission.status = "draft"
    flag_modified(submission, "payload")
    return submission


def can_edit_active_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    return False


def _assigned_agent_id(submission: PropertyListingSubmission) -> str | None:
    workflow = _workflow_from_submission(submission)
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
    if submission.status in DRAFT_STATUSES:
        return submission.submitted_by == user_id
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
    if submission.status in {ACTIVE_STATUS, DEACTIVATED_STATUS, DEAL_CLOSED_STATUS, DEAL_CLOSURE_REQUESTED_STATUS}:
        return False
    if submission.status in DRAFT_STATUSES:
        return submission.submitted_by == user_id
    workflow_stage = _workflow_stage_for_submission(submission)
    role_names = _role_names(roles)
    assigned_agent_id = _assigned_agent_id(submission)
    if workflow_stage in OWNER_EDIT_STAGES:
        return submission.submitted_by == user_id
    if workflow_stage in AGENT_EDIT_STAGES:
        if assigned_agent_id == str(user_id):
            return True
        if "agent" in role_names and submission.submitted_by == user_id:
            return True
        return False
    if submission.status in WORKING_STATUSES and submission.submitted_by == user_id and "admin" not in role_names:
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


def can_review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    role_names = _role_names(roles)
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return True
    return False


def assert_can_review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    if submission.status != PENDING_APPROVAL_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only pending submissions can be reviewed")
    if _workflow_stage_for_submission(submission) not in AGENCY_REVIEW_STAGES:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Submission must be returned by the assigned agent before review")
    if not can_review_submission(db, submission, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def create_revision_from_active(
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
    if source.status != ACTIVE_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only active submissions can create revisions")
    if not can_edit_active_submission(db, source, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Active property cannot be edited by this user")

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
        status=PENDING_APPROVAL_STATUS,
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
        message=f"Revision submitted for active property {revision.property_id}",
        user_id=user_id,
        property_id=revision.property_id,
    )
    return revision


def _next_workflow_stage_on_submit(
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
) -> str:
    role_names = _role_names(roles)
    current_stage = _workflow_stage_for_submission(submission)
    assigned_agent_id = _assigned_agent_id(submission)
    if current_stage in AGENT_EDIT_STAGES and (assigned_agent_id == str(user_id) or "agent" in role_names):
        return WORKFLOW_STAGE_AWAITING_AGENCY_REVIEW
    if current_stage in OWNER_EDIT_STAGES and assigned_agent_id:
        return WORKFLOW_STAGE_WITH_AGENT
    if "agent" in role_names:
        return WORKFLOW_STAGE_AWAITING_AGENCY_REVIEW
    return WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT


def submit_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None = None,
) -> PropertyListingSubmission:
    if submission.status in {ACTIVE_STATUS}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Active submissions cannot be resubmitted")
    if agency_id is not None and submission.status in {"draft", "rejected", "in_progress"}:
        submission.agency_id = agency_id
    resolve_listing_agency_or_400(db, submission.agency_id)
    assert_owner_agency_rule(db, user_id=user_id, agency_id=submission.agency_id, roles=roles)
    record_owner_agency_mapping_for_submission(db, user_id=user_id, agency_id=submission.agency_id, roles=roles)
    origin = _workflow_from_submission(submission).get("submission_origin") or _submission_origin_for_roles(roles)
    next_stage = _next_workflow_stage_on_submit(submission, user_id=user_id, roles=roles)
    assigned_agent_id = _assigned_agent_id(submission)
    if "agent" in _role_names(roles) and assigned_agent_id is None:
        assigned_agent_id = str(user_id)
    submission.status = PENDING_APPROVAL_STATUS
    submission.submitted_at = utc_now()
    submission.step_completion = compute_step_completion(submission.payload or {})
    _set_submission_workflow(
        submission,
        stage=next_stage,
        origin=origin,
        assigned_agent_id=assigned_agent_id,
        actor_user_id=user_id,
    )
    if next_stage == WORKFLOW_STAGE_WITH_AGENT:
        notify_assigned_agent_for_submission(db, submission=submission, actor_user_id=user_id)
    else:
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
    if not agency or not agency.is_active:
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
            action_url="/manage-listings",
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


def notify_assigned_agent_for_submission(db: Session, *, submission: PropertyListingSubmission, actor_user_id: UUID) -> None:
    agent_id = _assigned_agent_uuid(submission)
    if not agent_id:
        return
    recipient = db.get(User, agent_id)
    if not recipient:
        return
    payload = submission.payload or {}
    title = ((payload.get("basic_information") or {}).get("title")) or "property listing"
    create_in_app_notification(
        db,
        recipient_user_id=recipient.id,
        actor_user_id=actor_user_id,
        type_key="property_submission_assigned_for_update",
        title="Property submission assigned",
        message=f"Property submission for {title} is assigned to you for completion.",
        data={"submission_id": str(submission.id), "agency_id": str(submission.agency_id) if submission.agency_id else None},
        action_url="/my-listings",
    )
    send_email_notification(
        to_email=recipient.email,
        subject="Property submission assigned",
        body=f"Property submission for {title} is assigned to you for completion.",
    )
    if recipient.phone_number:
        send_sms_notification(
            to_phone=recipient.phone_number,
            body=f"Property submission for {title} is assigned to you for completion.",
        )


def review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    actor_id: UUID,
    action: str,
    reason: str | None = None,
) -> PropertyListingSubmission:
    if submission.status != PENDING_APPROVAL_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only pending submissions can be reviewed")
    workflow = _workflow_from_submission(submission)
    submission_origin = workflow.get("submission_origin") or SUBMISSION_ORIGIN_OWNER
    recipient_user_id = submission.submitted_by
    if action == "approve":
        submission.status = ACTIVE_STATUS
        submission.review_reason = None
        if not submission.property_id:
            submission.property_id = uuid4()
        _set_submission_workflow(
            submission,
            stage=WORKFLOW_STAGE_APPROVED,
            origin=submission_origin,
            actor_user_id=actor_id,
        )
    elif action == "reject":
        if not reason:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Rejection reason is required")
        submission.status = "rejected"
        submission.review_reason = reason
        assigned_agent_id = _assigned_agent_uuid(submission)
        rejected_stage = WORKFLOW_STAGE_RETURNED_TO_OWNER
        if submission_origin in {SUBMISSION_ORIGIN_AGENT, SUBMISSION_ORIGIN_AGENCY_ADMIN} and assigned_agent_id:
            rejected_stage = WORKFLOW_STAGE_RETURNED_TO_AGENT
            recipient_user_id = assigned_agent_id
        _set_submission_workflow(
            submission,
            stage=rejected_stage,
            origin=submission_origin,
            actor_user_id=actor_id,
        )
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
        recipient_user_id=recipient_user_id,
        actor_user_id=actor_id,
        type_key=f"property_submission_{submission.status}",
        title="Property submission reviewed",
        message=f"Your property submission was {submission.status}.",
        data={"submission_id": str(submission.id), "property_id": str(submission.property_id) if submission.property_id else None},
        action_url="/my-listings",
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
        "can_edit": submission.status in WORKING_STATUSES,
        "can_delete": submission.status in WORKING_STATUSES,
    }


def stable_property_hash(property_id: UUID) -> int:
    return property_id.int % 2147483647


def _can_edit_submission_for_actor(
    db: Session | None,
    submission: PropertyListingSubmission,
    *,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
) -> bool:
    if actor_user_id is None or db is None:
        return submission.status in WORKING_STATUSES
    if submission.status in {ACTIVE_STATUS, DEACTIVATED_STATUS}:
        return False
    return can_edit_working_submission(
        db,
        submission,
        user_id=actor_user_id,
        roles=actor_roles,
        agency_id=actor_agency_id,
    )


def _workflow_label_for_submission(submission: PropertyListingSubmission) -> str:
    workflow = (submission.payload or {}).get("_workflow") or {}
    if submission.status == ACTIVE_STATUS and workflow.get("deal_closure_status") == DEAL_CLOSURE_REQUESTED_STATUS:
        return DEAL_CLOSURE_REQUESTED_STATUS
    if submission.status == ACTIVE_STATUS and workflow.get("deal_closure_status") == DEAL_CLOSED_STATUS:
        return DEAL_CLOSED_STATUS
    return submission.status


def _status_display_name(status: str) -> str:
    labels = {
        ACTIVE_STATUS: "Active",
        DEACTIVATED_STATUS: "Deactivated",
        DEAL_CLOSED_STATUS: "Deal Closed",
        DEAL_CLOSURE_REQUESTED_STATUS: "Deal Closure Requested",
        PENDING_APPROVAL_STATUS: "Pending Approval",
        "draft": "Draft",
        "rejected": "Rejected",
        "in_progress": "In Progress",
    }
    return labels.get(status, status)


def serialize_agent_property_item(
    submission: PropertyListingSubmission,
    submitter: User | None = None,
    *,
    db: Session | None = None,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
) -> dict:
    payload = submission.payload or {}
    basic = payload.get("basic_information") or {}
    pricing = payload.get("pricing") or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    agency = None
    if submission.agency_id:
        agency = {"agency_id": str(submission.agency_id), "id": str(submission.agency_id)}
    assigned_agent = _assigned_agent_summary(db, submission) if db is not None else None
    workflow_label = _workflow_label_for_submission(submission)
    workflow_summary = _submission_workflow_summary(submission)
    can_edit_submission = _can_edit_submission_for_actor(
        db,
        submission,
        actor_user_id=actor_user_id,
        actor_roles=actor_roles,
        actor_agency_id=actor_agency_id,
    )
    can_delete_submission = submission.status in DRAFT_STATUSES and can_edit_submission
    return {
        "property_id": str(property_id),
        "property_hash": stable_property_hash(property_id),
        "title": basic.get("title") or "Untitled property",
        "listing_purpose": basic.get("listing_purpose") or "",
        "type_name": str(basic.get("type_id") or ""),
        "type_slug": str(basic.get("type_id") or ""),
        "category_name": str(basic.get("category_id") or ""),
        "category_slug": str(basic.get("category_id") or ""),
        "status_name": _status_display_name(workflow_label),
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
        "submission_workflow_label": workflow_label,
        **workflow_summary,
        "can_edit_submission": can_edit_submission,
        "can_delete_submission": can_delete_submission,
        "agency": agency,
        "submitted_by": submitter.full_name if submitter and submitter.full_name else str(submission.submitted_by),
        "agent_user_id": workflow.get("assigned_agent_id"),
        "agent_name": assigned_agent["name"] if assigned_agent else None,
        "agent_email": assigned_agent["email"] if assigned_agent else None,
        "agent_phone": assigned_agent["phone"] if assigned_agent else None,
    }


def serialize_admin_submission_item(submission: PropertyListingSubmission, submitter: User | None = None, *, db: Session | None = None) -> dict:
    payload = submission.payload or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    assigned_agent = _assigned_agent_summary(db, submission) if db is not None else None
    workflow_label = _workflow_label_for_submission(submission)
    workflow_summary = _submission_workflow_summary(submission)
    return {
        "submission_id": str(submission.id),
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
        "submitted_by": str(submission.submitted_by),
        "submitted_by_name": submitter.full_name if submitter else "",
        "status": workflow_label,
        "status_label": _status_display_name(workflow_label),
        **workflow_summary,
        "property_id": str(property_id),
        "agent_user_id": workflow.get("assigned_agent_id"),
        "agent_name": assigned_agent["name"] if assigned_agent else None,
        "agent_email": assigned_agent["email"] if assigned_agent else None,
        "agent_phone": assigned_agent["phone"] if assigned_agent else None,
        "has_assigned_agent": bool(workflow.get("assigned_agent_id")),
        "property_hash": stable_property_hash(property_id),
        "property_title": _title(payload) or "Untitled property",
        "property_reference_number": (payload.get("property_details") or {}).get("reference_number"),
        "current_step": submission.current_step,
        "submitted_at": _iso(submission.submitted_at) or _iso(submission.created_at),
        "reviewed_at": _iso(submission.reviewed_at),
        "review_reason": submission.review_reason,
    }


def list_submissions(
    db: Session,
    *,
    page: int,
    page_size: int,
    statuses: set[str] | None = None,
    submitted_by: UUID | None = None,
    assigned_to: UUID | None = None,
    agency_id: UUID | None = None,
    exclude_drafts: bool = False,
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
    if exclude_drafts:
        stmt = stmt.where(PropertyListingSubmission.status.not_in(DRAFT_STATUSES))
    if submitted_by and assigned_to:
        stmt = stmt.where(
            or_(
                PropertyListingSubmission.submitted_by == submitted_by,
                PropertyListingSubmission.payload["_workflow"]["assigned_agent_id"].astext == str(assigned_to),
            )
        )
    elif submitted_by:
        stmt = stmt.where(PropertyListingSubmission.submitted_by == submitted_by)
    elif assigned_to:
        stmt = stmt.where(PropertyListingSubmission.payload["_workflow"]["assigned_agent_id"].astext == str(assigned_to))
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
    actor_user_id: UUID,
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
    role_names = _role_names(actor_roles)
    if "admin" not in role_names or "super_admin" in role_names:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin can assign agents")
    assert_can_manage_submission(db, submission, roles=actor_roles, agency_id=actor_agency_id)
    workflow_stage = _workflow_stage_for_submission(submission)
    can_assign_active = _workflow_label_for_submission(submission) == ACTIVE_STATUS
    can_assign_pending = submission.status == PENDING_APPROVAL_STATUS and workflow_stage in ASSIGNMENT_READY_STAGES
    if not can_assign_active and not can_assign_pending:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agent assignment is not available in the current workflow stage")
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
    if submission.status == PENDING_APPROVAL_STATUS:
        if agent_id:
            workflow["workflow_stage"] = WORKFLOW_STAGE_WITH_AGENT
            workflow["current_actor"] = CURRENT_ACTOR_ASSIGNED_AGENT
            workflow.setdefault("submission_origin", SUBMISSION_ORIGIN_OWNER)
        else:
            workflow["workflow_stage"] = WORKFLOW_STAGE_AWAITING_AGENCY_ASSIGNMENT
            workflow["current_actor"] = CURRENT_ACTOR_AGENCY_ADMIN
        workflow["last_transition_at"] = utc_now().isoformat()
    submission.payload = payload
    flag_modified(submission, "payload")
    if submission.status == PENDING_APPROVAL_STATUS and agent_id:
        notify_assigned_agent_for_submission(db, submission=submission, actor_user_id=actor_user_id)
    return submission


def deactivate_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    actor_id: UUID,
) -> PropertyListingSubmission:
    if _workflow_label_for_submission(submission) != ACTIVE_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only active properties can be deactivated")
    submission.status = DEACTIVATED_STATUS
    record_activity(
        db,
        activity_type="property_deactivated",
        message=f"Property submission {submission.id} deactivated",
        user_id=actor_id,
        property_id=submission.property_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=submission.submitted_by,
        actor_user_id=actor_id,
        type_key="property_deactivated",
        title="Property deactivated",
        message="Your property listing was deactivated.",
        data={"submission_id": str(submission.id), "property_id": str(submission.property_id) if submission.property_id else None},
        action_url="/my-listings",
    )
    return submission
