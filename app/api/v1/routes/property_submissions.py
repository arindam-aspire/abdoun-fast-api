"""Endpoints for list-your-property submission workflow."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.property_submissions import get_property_submission_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User
from app.schemas.property_submission import (
    CreatePropertySubmissionRequest,
    PropertySubmissionCreateResponse,
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
    """Create a draft property submission for the current user."""
    data = service.create_submission(user=current_user, body=body)
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
    """Save any step payload for an in-progress submission."""
    data = service.patch_submission(submission_id=submission_id, body=body, user=current_user)
    return create_success_response(data=data, message=None)


@router.post("/{submission_id}/submit", response_model=StandardResponse[PropertySubmissionSubmitResponse])
def submit_submission(
    submission_id: uuid.UUID,
    body: PropertySubmissionSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Final submit: validate and persist into normalized property tables."""
    data = service.submit_submission(submission_id=submission_id, body=body, user=current_user)
    return create_success_response(data=data, message=None)
