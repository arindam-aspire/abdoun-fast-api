from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.schemas.agents import AgentInviteRequest, AgentStatusUpdateRequest
from app.services.agents import invite_agent, list_agents, update_agent_status
from app.utils.api_response import success_response

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.get("")
def get_agents(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    sortBy: str = "invited_at",
    sortOrder: str = "desc",
) -> dict:
    data = list_agents(
        db,
        agency_id=context.agency_id,
        roles=context.roles,
        page=page,
        page_size=pageSize,
        sort_by=sortBy,
        sort_order=sortOrder,
    )
    return success_response(data, meta={"pagination": data["pagination"]})


@router.post("/invite")
def create_agent_invite(payload: AgentInviteRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    agent = invite_agent(
        db,
        email=payload.email,
        invited_by=context.user_id,
        agency_id=context.agency_id,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        service_area=payload.service_area,
    )
    db.commit()
    return success_response(agent, "Agent invitation logged in dev mode")


@router.patch("/{agent_id}/status")
def set_agent_status(
    agent_id: UUID,
    payload: AgentStatusUpdateRequest,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    agent = update_agent_status(
        db,
        agent_id=agent_id,
        actor_id=context.user_id,
        status=payload.status,
        reason=payload.reason,
    )
    db.commit()
    return success_response(agent, "Agent status updated")
