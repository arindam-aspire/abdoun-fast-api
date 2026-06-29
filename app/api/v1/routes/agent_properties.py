from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.services.property_submissions import (
    ACTIVE_STATUS,
    list_submissions,
    serialize_agent_property_item,
    serialize_draft_list_item,
)
from app.utils.api_response import success_response

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.get("")
def get_agent_properties(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    status: str | None = None,
    search: str | None = None,
) -> dict:
    statuses = {status} if status else {ACTIVE_STATUS}
    rows, pagination = list_submissions(
        db,
        page=page,
        page_size=pageSize,
        statuses=statuses,
        submitted_by=context.user_id if "super_admin" not in {role.lower() for role in context.roles} else None,
        exclude_drafts=True,
    )
    items = [serialize_agent_property_item(submission, submitter) for submission, submitter in rows]
    if search:
        lowered = search.lower()
        items = [item for item in items if lowered in item["title"].lower()]
    data = {"items": items, **pagination}
    return success_response(data, meta={"pagination": pagination})


@router.get("/drafts")
def get_agent_property_drafts(
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
    data = {"items": [serialize_draft_list_item(submission) for submission, _ in rows], **pagination}
    return success_response(data, meta={"pagination": pagination})
