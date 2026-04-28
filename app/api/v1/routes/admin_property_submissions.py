"""Admin moderation endpoints for property submissions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.property_submissions import get_property_submission_service
from app.api.v1.deps.security import require_role
from app.models.user import User
from app.schemas.property_submission import (
    AdminSubmissionDetailResponse,
    AdminSubmissionListResponse,
    AdminSubmissionReviewRequest,
    AdminSubmissionReviewResponse,
)
from app.services.property_submission_service import PropertySubmissionService
from app.utils.constants import UserRoles
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get("", response_model=StandardResponse[AdminSubmissionListResponse])
def list_submissions_for_admin(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=200),
):
    """List submissions for moderation with optional status filter.

    Excludes agent-only rows (**draft**, **in_progress**); only the moderation queue
    (**submitted**, **changes_requested**, **approved**, **rejected**) appears.
    """
    data = service.list_admin_submissions(status=status, page=page, limit=limit)
    return create_success_response(data=data, message=None)


@router.get("/{submission_id}", response_model=StandardResponse[AdminSubmissionDetailResponse])
def get_submission_for_admin(
    submission_id: uuid.UUID,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Get one submission details for moderation."""
    data = service.get_admin_submission(submission_id=submission_id)
    return create_success_response(data=data, message=None)


@router.post(
    "/{submission_id}/review",
    response_model=StandardResponse[AdminSubmissionReviewResponse],
)
def review_submission_for_admin(
    submission_id: uuid.UUID,
    body: AdminSubmissionReviewRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
):
    """Moderate a submitted property submission."""
    data = service.review_submission(
        submission_id=submission_id,
        admin_user=current_user,
        body=body,
    )
    return create_success_response(data=data, message=None)
