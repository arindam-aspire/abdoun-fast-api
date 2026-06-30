from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_any_role
from app.schemas.agents import (
    AgentInvitationAcceptRequest,
    AgentInviteRequest,
    AgentStatusUpdateRequest,
    ManualOnboardAgentRequest,
)
from app.services.agents import (
    accept_agent_invitation,
    agent_summary,
    delete_agent,
    invite_agent,
    list_agents,
    manual_onboard_agent,
    resend_agent_invitation,
    validate_agent_invitation,
    update_agent_status,
)
from app.utils.api_response import success_response

router = APIRouter()

AgentListContext = Annotated[RequestContext, Depends(require_any_role("admin", "super_admin"))]
AgencyAdminContext = Annotated[RequestContext, Depends(require_any_role("admin"))]


@router.get("")
def get_agents(
    context: AgentListContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    sortBy: str = "invited_at",
    sortOrder: str = "desc",
    search: str | None = None,
    status: str | None = None,
) -> dict:
    data = list_agents(
        db,
        agency_id=context.agency_id,
        roles=context.roles,
        page=page,
        page_size=pageSize,
        sort_by=sortBy,
        sort_order=sortOrder,
        search=search,
        status=status,
    )
    return success_response(data, meta={"pagination": data["pagination"]})


@router.get("/summary")
def get_agent_summary(context: AgentListContext, db: DBSessionDep) -> dict:
    return success_response(agent_summary(db, agency_id=context.agency_id, roles=context.roles))


@router.post("/invite")
def create_agent_invite(payload: AgentInviteRequest, context: AgencyAdminContext, db: DBSessionDep) -> dict:
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


@router.get("/invitations/validate")
def validate_invitation(token: str, db: DBSessionDep) -> dict:
    return success_response(validate_agent_invitation(db, token=token))


@router.post("/invitations/accept")
def accept_invitation(payload: AgentInvitationAcceptRequest, db: DBSessionDep) -> dict:
    agent = accept_agent_invitation(db, token=payload.token, password=payload.password)
    db.commit()
    return success_response(agent, "Agent account activated successfully")


@router.post("/manual-onboard")
def create_manual_agent(payload: ManualOnboardAgentRequest, context: AgencyAdminContext, db: DBSessionDep) -> dict:
    agent = manual_onboard_agent(
        db,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        service_area=payload.service_area,
        actor_id=context.user_id,
        agency_id=context.agency_id,
    )
    db.commit()
    return success_response(agent, "Agent onboarded successfully")


@router.post("/{agent_id}/resend-invitation")
def resend_invitation(agent_id: UUID, context: AgencyAdminContext, db: DBSessionDep) -> dict:
    invite = resend_agent_invitation(
        db,
        agent_id=agent_id,
        actor_id=context.user_id,
        agency_id=context.agency_id,
    )
    db.commit()
    return success_response(invite, "Agent invitation resent")


@router.delete("/{agent_id}")
def remove_agent(agent_id: UUID, context: AgencyAdminContext, db: DBSessionDep) -> dict:
    delete_agent(
        db,
        agent_id=agent_id,
        actor_id=context.user_id,
        agency_id=context.agency_id,
    )
    db.commit()
    return success_response(True, "Agent removed")


@router.patch("/{agent_id}/status")
def set_agent_status(
    agent_id: UUID,
    payload: AgentStatusUpdateRequest,
    context: AgencyAdminContext,
    db: DBSessionDep,
) -> dict:
    agent = update_agent_status(
        db,
        agent_id=agent_id,
        actor_id=context.user_id,
        actor_agency_id=context.agency_id,
        status=payload.status,
        reason=payload.reason,
    )
    db.commit()
    return success_response(agent, "Agent status updated")
