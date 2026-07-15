from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import DBSessionDep, RequestContext, require_any_role
from app.schemas.agents import (
    AgentDocumentUploadRequest,
    AgentInvitationAcceptRequest,
    AgentInviteRequest,
    AgentOnboardingFormRequest,
    AgentPasswordSetupRequest,
    AgentStatusUpdateRequest,
    ManualOnboardAgentRequest,
)
from app.services.agents import (
    accept_agent_invitation,
    agent_summary,
    complete_agent_password_setup,
    create_agent_document_upload,
    delete_agent,
    invite_agent,
    list_agents,
    manual_onboard_agent,
    resend_agent_invitation,
    submit_agent_onboarding,
    validate_agent_invitation,
    update_agent_status,
)
from app.utils.api_response import raise_api_error, success_response
from app.utils.status_codes import STATUS_BAD_REQUEST

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
        phone_number=payload.phone_number,
        invited_by=context.user_id,
        agency_id=context.agency_id,
        full_name=payload.full_name,
        service_area=payload.service_area,
    )
    db.commit()
    return success_response(agent, "Agent invitation logged in dev mode")


@router.get("/invitations/validate")
@router.get("/invite/validate")
def validate_invitation(token: str, db: DBSessionDep) -> dict:
    return success_response(validate_agent_invitation(db, token=token))


@router.post("/invitations/accept")
def accept_invitation(payload: AgentInvitationAcceptRequest, db: DBSessionDep) -> dict:
    agent = accept_agent_invitation(db, token=payload.token, password=payload.password)
    db.commit()
    return success_response(
        agent,
        "Password set successfully. Your account is pending admin approval.",
    )


@router.post("/invitations/submit")
@router.post("/onboarding")
def submit_onboarding(
    payload: AgentOnboardingFormRequest,
    db: DBSessionDep,
    token: str | None = Query(default=None),
) -> dict:
    invite_token = payload.token or token
    if not invite_token:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invitation token is required",
        )
    agent = submit_agent_onboarding(
        db,
        token=invite_token,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        whatsapp_number=payload.whatsapp_number,
        service_area_ids=payload.service_area_ids,
        service_area=payload.service_area,
        position=payload.position,
        identity_document_url=payload.identity_document_url,
    )
    db.commit()
    return success_response(agent, "Agent onboarding submitted; password setup link logged in dev mode")


@router.post("/password/setup")
def setup_agent_password(payload: AgentPasswordSetupRequest, db: DBSessionDep) -> dict:
    agent = complete_agent_password_setup(db, token=payload.token, password=payload.password)
    db.commit()
    return success_response(
        agent,
        "Password set successfully. Your account is pending admin approval.",
    )


@router.post("/invitations/document-upload")
def request_identity_document_upload(payload: AgentDocumentUploadRequest, db: DBSessionDep) -> dict:
    upload = create_agent_document_upload(
        db,
        token=payload.token,
        file_name=payload.file_name,
        content_type=payload.content_type,
        file_size=payload.file_size,
    )
    return success_response(upload, "Agent identity document upload URL generated")


@router.post("/manual-onboard")
def create_manual_agent(payload: ManualOnboardAgentRequest, context: AgencyAdminContext, db: DBSessionDep) -> dict:
    agent = manual_onboard_agent(
        db,
        full_name=payload.full_name,
        email=str(payload.email),
        phone=payload.phone,
        whatsapp_number=payload.whatsapp_number,
        service_area_ids=payload.service_area_ids,
        service_area=payload.service_area,
        position=payload.position,
        identity_document_url=payload.identity_document_url,
        actor_id=context.user_id,
        agency_id=context.agency_id,
    )
    db.commit()
    return success_response(agent, "Agent onboarded; password setup link logged in dev mode")


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
    status = str(agent.get("status") or "").upper()
    if status == "ACTIVE":
        message = "Agent approved and activated successfully"
    elif status == "DECLINED":
        message = "Agent declined successfully"
    elif status == "PENDING_REVIEW":
        message = "Agent marked as pending admin approval"
    elif status == "INACTIVE":
        message = "Agent deactivated successfully"
    else:
        message = f"Agent status updated to {status}"
    return success_response(agent, message)
