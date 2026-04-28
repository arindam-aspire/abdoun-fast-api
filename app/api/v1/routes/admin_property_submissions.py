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
    AdminPropertySubmissionSubmitExistingRequest,
    CreateAndSubmitPropertySubmissionRequest,
    PropertySubmissionSubmitResponse,
    PropertySubmissionDeleteResponse,
)
from app.schemas.admin_property_drafts import AdminDraftSubmissionItem, AdminDraftSubmissionListResponse
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
    include_deleted: bool = Query(default=False, description="Include soft-deleted submissions in results."),
):
    """List submissions for moderation with optional status filter.

    Excludes agent-only rows (**draft**, **in_progress**); only the moderation queue
    (**submitted**, **changes_requested**, **approved**, **rejected**) appears.
    """
    data = service.list_admin_submissions(status=status, page=page, limit=limit, include_deleted=include_deleted)
    return create_success_response(data=data, message=None)


@router.get(
    "/drafts",
    response_model=StandardResponse[AdminDraftSubmissionListResponse],
)
def list_admin_draft_submissions(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
):
    """List admin's draft/in_progress wizard submissions (no property_id yet)."""
    payload = service.list_my_draft_submissions(user=current_user, page=page, limit=limit)
    return create_success_response(
        data=AdminDraftSubmissionListResponse(
            items=[AdminDraftSubmissionItem(**i) for i in payload["items"]],
            total=int(payload["total"]),
            page=int(payload["page"]),
            limit=int(payload["limit"]),
        ),
        message=None,
    )


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


@router.post(
    "/submit",
    response_model=StandardResponse[PropertySubmissionSubmitResponse],
)
def admin_create_and_submit_approved(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    body: CreateAndSubmitPropertySubmissionRequest,
):
    """Admin creates a property and it is approved immediately (no pending review)."""
    data = service.admin_create_and_approve_submission(admin_user=current_user, body=body)
    return create_success_response(data=data, message=None)


@router.post(
    "/{submission_id}/submit",
    response_model=StandardResponse[PropertySubmissionSubmitResponse],
)
def admin_submit_existing_draft(
    submission_id: uuid.UUID,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    body: AdminPropertySubmissionSubmitExistingRequest,
):
    """Admin submits an existing draft and it is approved immediately."""
    data = service.admin_submit_existing_draft_and_approve(
        submission_id=submission_id,
        admin_user=current_user,
        confirm_submit=body.confirm_submit,
    )
    return create_success_response(data=data, message=None)


@router.delete(
    "/{submission_id}",
    response_model=StandardResponse[PropertySubmissionDeleteResponse],
)
def admin_soft_delete_submission(
    submission_id: uuid.UUID,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertySubmissionService, Depends(get_property_submission_service)],
    reason: str | None = Query(default=None, description="Optional deletion reason (soft delete)."),
):
    """Admin soft delete a submission and linked property (if any)."""
    data = service.admin_soft_delete_submission(submission_id=submission_id, admin_user=current_user, reason=reason)
    return create_success_response(data=data, message=None)
