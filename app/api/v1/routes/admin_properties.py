from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_any_role
from app.schemas.property_submissions import PropertyAssignAgentRequest, PropertySubmissionReviewRequest
from app.services.property_submissions import (
    assign_agent_to_property,
    assert_can_manage_submission,
    get_submission_or_404,
    list_submissions,
    review_submission,
    serialize_admin_submission_item,
    serialize_submission,
)
from app.utils.api_response import success_response

router = APIRouter()

AdminContext = Annotated[RequestContext, Depends(require_any_role("admin", "super_admin"))]
SuperAdminContext = Annotated[RequestContext, Depends(require_any_role("super_admin"))]


@router.get("/property-submissions")
def get_admin_property_submissions(
    context: AdminContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    status: str | None = None,
) -> dict:
    roles = {role.lower() for role in context.roles}
    if "super_admin" not in roles and context.agency_id is None:
        pagination = {"total": 0, "page": max(page, 1), "pageSize": max(min(pageSize, 100), 1), "totalPages": 1, "hasNext": False, "hasPrevious": False}
        return success_response({"items": [], **pagination}, meta={"pagination": pagination})
    rows, pagination = list_submissions(
        db,
        page=page,
        page_size=pageSize,
        statuses={status} if status else None,
        agency_id=None if "super_admin" in roles else context.agency_id,
        exclude_drafts=True,
    )
    data = {"items": [serialize_admin_submission_item(submission, submitter, db=db) for submission, submitter in rows], **pagination}
    return success_response(data, meta={"pagination": pagination})


@router.post("/property-submissions/{submission_id}/review")
def review_admin_property_submission(
    submission_id: UUID,
    payload: PropertySubmissionReviewRequest,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    submission = get_submission_or_404(db, submission_id)
    assert_can_manage_submission(db, submission, roles=context.roles, agency_id=context.agency_id)
    review_submission(
        db,
        submission,
        actor_id=context.user_id,
        action=payload.action,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property submission reviewed")


@router.patch("/properties/{property_id}/assign-agent")
def assign_admin_property_agent(
    property_id: UUID,
    payload: PropertyAssignAgentRequest,
    context: AdminContext,
    db: DBSessionDep,
) -> dict:
    agent_id = UUID(payload.agent_id) if payload.agent_id else None
    submission = assign_agent_to_property(
        db,
        property_id=property_id,
        agent_id=agent_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    db.commit()
    db.refresh(submission)
    return success_response(serialize_submission(submission), "Property agent assignment updated")
