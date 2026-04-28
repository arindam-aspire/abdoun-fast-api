"""Endpoints for list-your-property submission workflow."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.property_submissions import get_property_submission_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User
from app.schemas.property_submission import (
    CreateAndSubmitPropertySubmissionRequest,
    CreatePropertySubmissionRequest,
    PropertySubmissionCreateResponse,
    PropertySubmissionDeleteResponse,
    PropertySubmissionDetailResponse,
    PropertySubmissionPatchRequest,
    PropertySubmissionPatchResponse,
    PropertySubmissionSubmitRequest,
    PropertySubmissionSubmitResponse,
)
from app.services.property_submission_service import PropertySubmissionService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.post("", response_model=StandardResponse[PropertySubmissionCreateResponse])
def create_submission(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    body: CreatePropertySubmissionRequest | None = None,
):
    """Persist a draft: primary path is ``payload`` (Save as Draft with full stepper state from local/Redux).

    Empty or omitted body remains supported for backward compatibility (older clients that created a row on entry).
    """
    data = service.create_submission(user=current_user, body=body)
    return create_success_response(data=data, message=None)


@router.post(
    "/submit",
    response_model=StandardResponse[PropertySubmissionSubmitResponse],
)
def create_and_submit(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    body: CreateAndSubmitPropertySubmissionRequest,
):
    """Create a submission, validate, and submit in one atomic flow (e.g. Redux-first with no prior ``submission_id``)."""
    data = service.create_and_submit_submission(user=current_user, body=body)
    return create_success_response(data=data, message=None)


@router.get("/{submission_id}", response_model=StandardResponse[PropertySubmissionDetailResponse])
def get_submission(
    submission_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Get one submission by id for current owner user."""
    data = service.get_submission(submission_id=submission_id, user=current_user)
    return create_success_response(data=data, message=None)


@router.patch("/{submission_id}", response_model=StandardResponse[PropertySubmissionPatchResponse])
def patch_submission(
    submission_id: uuid.UUID,
    body: PropertySubmissionPatchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Save progress: per-step (``step`` + ``data``) or full form (``payload`` + ``action=save_draft`` + ``current_step``)."""
    data = service.patch_submission(submission_id=submission_id, body=body, user=current_user)
    return create_success_response(data=data, message=None)


@router.post("/{submission_id}/submit", response_model=StandardResponse[PropertySubmissionSubmitResponse])
def submit_submission(
    submission_id: uuid.UUID,
    body: PropertySubmissionSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Final submit: validate and persist into normalized property tables.

    After admin **reject**, the agent can edit and call this again to re-enter **submitted** (pending review).
    """
    data = service.submit_submission(submission_id=submission_id, body=body, user=current_user)
    return create_success_response(data=data, message=None)


@router.delete("/{submission_id}", response_model=StandardResponse[PropertySubmissionDeleteResponse])
def delete_submission(
    submission_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Abandon a draft, delete after rejection, or clear *changes requested*; not allowed when pending or approved.

    **Edit** remains ``PATCH /{submission_id}``; use this to remove a submission the agent is allowed to drop.
    """
    data = service.delete_submission(submission_id=submission_id, user=current_user)
    return create_success_response(data=data, message=None)
