from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.schemas.property_submissions import (
    PropertySubmissionCreateRequest,
    PropertySubmissionDirectSubmitRequest,
    PropertySubmissionSubmitRequest,
    PropertySubmissionUpdateRequest,
)
from app.services.property_submissions import (
    assert_can_delete_submission,
    assert_can_edit_working_submission,
    assert_can_view_submission,
    create_submission,
    get_submission_or_404,
    list_submissions,
    owner_may_submit_without_agency,
    serialize_draft_list_item,
    serialize_submission,
    soft_delete_submission,
    submit_submission,
    update_submission,
)
from app.services.audit import record_activity
from app.utils.api_response import raise_api_error, success_response
from app.utils.status_codes import STATUS_BAD_REQUEST

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def _resolved_agency_id(
    route_through_agency: bool,
    payload_agency_id: UUID | None,
    context: RequestContext,
) -> UUID | None:
    if owner_may_submit_without_agency(context.roles, route_through_agency):
        return None
    return payload_agency_id or context.agency_id


@router.post("")
def create_property_submission(
    payload: PropertySubmissionCreateRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    submission = create_submission(
        db,
        user_id=context.user_id,
        roles=context.roles,
        route_through_agency=payload.route_through_agency,
        agency_id=_resolved_agency_id(payload.route_through_agency, payload.agency_id, context),
        payload=payload.payload,
        current_step=payload.current_step,
        last_completed_step=payload.last_completed_step,
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property draft saved")


@router.post("/submit")
def submit_new_property_submission(
    payload: PropertySubmissionDirectSubmitRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    if not payload.confirm_submit:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Property submission must be confirmed",
            details=[
                {
                    "field": "confirm_submit",
                    "code": "missing_required_field",
                    "message": "Property submission must be confirmed",
                }
            ],
        )
    submission = create_submission(
        db,
        user_id=context.user_id,
        roles=context.roles,
        route_through_agency=payload.route_through_agency,
        agency_id=_resolved_agency_id(payload.route_through_agency, payload.agency_id, context),
        payload=payload.payload,
        current_step=8,
        last_completed_step=8,
    )
    submit_submission(
        db,
        submission,
        user_id=context.user_id,
        roles=context.roles,
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property submitted for approval")


@router.get("/drafts")
def list_property_submission_drafts(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
) -> dict:
    rows, pagination = list_submissions(
        db,
        page=page,
        page_size=pageSize,
        statuses={"draft"},
        submitted_by=context.user_id,
    )
    data = {
        "items": [
            serialize_draft_list_item(
                submission,
                db=db,
                actor_user_id=context.user_id,
                actor_roles=context.roles,
                actor_agency_id=context.agency_id,
            )
            for submission, _ in rows
        ],
        **pagination,
    }
    return success_response(data, meta={"pagination": pagination})


@router.get("/{submission_id}")
def get_property_submission(submission_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    submission = get_submission_or_404(db, submission_id)
    assert_can_view_submission(db, submission, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    return success_response(serialize_submission(submission))


@router.patch("/{submission_id}")
def update_property_submission(
    submission_id: UUID,
    payload: PropertySubmissionUpdateRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    submission = get_submission_or_404(db, submission_id)
    assert_can_edit_working_submission(db, submission, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    effective_route = (
        payload.route_through_agency
        if payload.route_through_agency is not None
        else bool(getattr(submission, "route_through_agency", False))
    )
    update_submission(
        db,
        submission,
        user_id=context.user_id,
        roles=context.roles,
        route_through_agency=payload.route_through_agency,
        agency_id=_resolved_agency_id(effective_route, payload.agency_id, context),
        payload=payload.payload,
        current_step=payload.current_step,
        last_completed_step=payload.last_completed_step,
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property draft saved")


@router.delete("/{submission_id}")
def delete_property_submission(submission_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    submission = get_submission_or_404(db, submission_id)
    assert_can_delete_submission(db, submission, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    soft_delete_submission(
        submission,
        deleted_by=context.user_id,
        reason="Rejected property deleted by authorized workflow actor"
        if submission.status == "rejected"
        else "Draft property deleted by user",
    )
    record_activity(
        db,
        activity_type="property_submission_soft_deleted",
        message=f"Property submission {submission.id} was soft deleted",
        user_id=context.user_id,
        property_id=submission.property_id,
    )
    db.commit()
    return success_response(
        {"submission_id": str(submission.id), "deleted": True},
        "Property deleted successfully.",
    )


@router.post("/{submission_id}/submit")
def submit_existing_property_submission(
    submission_id: UUID,
    payload: PropertySubmissionSubmitRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    if not payload.confirm_submit:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Property submission must be confirmed",
            details=[
                {
                    "field": "confirm_submit",
                    "code": "missing_required_field",
                    "message": "Property submission must be confirmed",
                }
            ],
        )
    submission = get_submission_or_404(db, submission_id)
    assert_can_edit_working_submission(db, submission, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    submit_submission(
        db,
        submission,
        user_id=context.user_id,
        roles=context.roles,
        agency_id=context.agency_id,
        review_comment=payload.review_comment,
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property submitted for approval")
