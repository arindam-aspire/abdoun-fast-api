"""Authenticated list of properties created by the current user (agent dashboard)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.agent_properties import get_agent_property_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User
from app.schemas.agent_properties import AgentDraftSubmissionListResponse, AgentPropertyListResponse
from app.services.agent_property_service import AgentPropertyService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get(
    "",
    response_model=StandardResponse[AgentPropertyListResponse],
    response_model_exclude_unset=True,
)
def list_agent_properties(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgentPropertyService, Depends(get_agent_property_service)],
    page: int = Query(default=1, ge=1, description="1-based page"),
    limit: int = Query(default=20, ge=1, le=200, description="Page size (max 200)"),
    include_drafts: bool = Query(
        default=False,
        description="When true, include `draft_submissions` in the response. Prefer using `/agent-properties/drafts`.",
    ),
):
    """Return properties where ``created_by`` is the current user, plus submission workflow metadata.

    Each **item** may include ``submission_id`` / ``submission_status`` when the row is linked to
    ``property_listing_submissions`` (use for badges like *Pending admin approval* vs catalog
    ``status_slug`` from ``property_status``). **draft_submissions** lists in-progress wizards
    with no ``property_id`` yet (matches extra rows you see only in that SQL table).
    """
    data = service.list_my_properties(user=current_user, page=page, limit=limit, include_drafts=include_drafts)
    return create_success_response(data=data, message=None)


@router.get("/drafts", response_model=StandardResponse[AgentDraftSubmissionListResponse])
def list_agent_drafts(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgentPropertyService, Depends(get_agent_property_service)],
    page: int = Query(default=1, ge=1, description="1-based page"),
    limit: int = Query(default=20, ge=1, le=200, description="Page size (max 200)"),
):
    """Draft-only list for the agent dashboard (no normalized property row yet)."""
    data = service.list_my_draft_submissions(user=current_user, page=page, limit=limit)
    return create_success_response(data=data, message=None)
