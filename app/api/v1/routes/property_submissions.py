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
    create_submission,
    get_submission_or_404,
    serialize_submission,
    soft_delete_submission,
    submit_submission,
    update_submission,
)
from app.utils.api_response import success_response

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.post("")
def create_property_submission(
    payload: PropertySubmissionCreateRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    submission = create_submission(
        db,
        user_id=context.user_id,
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
    submission = create_submission(
        db,
        user_id=context.user_id,
        payload=payload.payload,
        current_step=8,
        last_completed_step=8,
        status="submitted",
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property submitted for approval")


@router.get("/{submission_id}")
def get_property_submission(submission_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    submission = get_submission_or_404(db, submission_id)
    return success_response(serialize_submission(submission))


@router.patch("/{submission_id}")
def update_property_submission(
    submission_id: UUID,
    payload: PropertySubmissionUpdateRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    submission = get_submission_or_404(db, submission_id)
    update_submission(
        submission,
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
    soft_delete_submission(submission, deleted_by=context.user_id)
    db.commit()
    return success_response(True, "Property draft deleted")


@router.post("/{submission_id}/submit")
def submit_existing_property_submission(
    submission_id: UUID,
    payload: PropertySubmissionSubmitRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    submission = get_submission_or_404(db, submission_id)
    submit_submission(submission)
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property submitted for approval")
