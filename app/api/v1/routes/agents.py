"""
Agent routes: invite, onboarding, admin CRUD, assignments.
All behaviour delegated to AgentService; no DB or business logic in this module.
"""

import json
import math
import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import ValidationError

from app.api.v1.deps.agents import get_agent_service
from app.api.v1.deps.security import require_role
from app.models.user import User
from app.schemas.user import (
    AdminAgentAssignmentRequest,
    AdminAgentAssignmentResponse,
    AdminCreateAgentRequest,
    AdminCreateAgentResponse,
    AgentAcceptResponse,
    AgentDeclineResponse,
    AgentDeleteResponse,
    AgentDetailResponse,
    AgentInviteRequest,
    AgentInviteResponse,
    AgentListResponse,
    AgentListPaginatedResponse,
    AgentOnboardingFormRequest,
    AgentOnboardingFormResponse,
    AgentStatusUpdateRequest,
    AgentStatusUpdateResponse,
    AgentValidateInviteResponse,
    PaginationInfo,
)
from app.services.agent_service import AgentService
from app.utils.constants import ApiDocs, Defaults, UserRoles
from app.utils.responses import StandardResponse, create_success_response
from app.utils.constants import ErrorMessages, SuccessMessages
from app.utils.status_codes import HTTPStatus
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger

router = APIRouter()


def _sanitize_validation_errors(errors: List[dict]) -> List[dict]:
    """Make validation error context JSON-serializable.

    Args:
        errors: List of Pydantic error dicts (e.g. from ValidationError.errors()).

    Returns:
        Copy of errors with ctx values stringified where not JSON-serializable.
    """
    sanitized = []
    for err in errors:
        clean = dict(err)
        ctx = clean.get("ctx")
        if ctx:
            clean_ctx = {}
            for key, value in ctx.items():
                if isinstance(value, BaseException):
                    clean_ctx[key] = str(value)
                else:
                    try:
                        json.dumps(value)
                        clean_ctx[key] = value
                    except TypeError:
                        clean_ctx[key] = str(value)
            clean["ctx"] = clean_ctx
        sanitized.append(clean)
    return sanitized


# ============================================================================
# Admin Endpoints
# ============================================================================


@router.post("/invite", response_model=StandardResponse[AgentInviteResponse])
def invite_agent(
    invite_in: AgentInviteRequest,
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentInviteResponse]:
    """
    Admin: Invite an agent.
    Creates an AgentInvite record and sends an invite email.
    """
    data = service.invite_agent(invite_in, current_user)
    return create_success_response(
        data=AgentInviteResponse(**data),
        message=SuccessMessages.AGENT_INVITE_SENT_TO.format(email=invite_in.email),
    )


@router.post("/manual-onboard", response_model=StandardResponse[AdminCreateAgentResponse])
def create_agent_direct(
    body: AdminCreateAgentRequest,
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AdminCreateAgentResponse]:
    """
    Admin: directly create an agent (no invite flow) with a temporary password.
    """
    data = service.create_agent_direct(body, current_user)
    return create_success_response(
        data=AdminCreateAgentResponse(**data),
        message=SuccessMessages.AGENT_CREATED_WITH_TEMP_PASSWORD,
    )


@router.get("", response_model=StandardResponse[AgentListPaginatedResponse])
def list_agents(
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
    status: Optional[str] = Query(None, description=ApiDocs.FILTER_BY_STATUS),
    search: Optional[str] = Query(None, description=ApiDocs.SEARCH_BY_NAME_OR_EMAIL),
    page: int = Query(1, ge=1, description=ApiDocs.PAGE_NUMBER),
    limit: int = Query(20, ge=1, le=100, description=ApiDocs.ITEMS_PER_PAGE),
    sortBy: str = Query("invitedAt", description=ApiDocs.SORT_FIELD),
    sortOrder: str = Query("desc", description=ApiDocs.SORT_ORDER),
) -> StandardResponse[AgentListPaginatedResponse]:
    """Admin: List agents with pagination and filtering."""
    agents_data, total_items = service.list_agents(
        status=status,
        search=search,
        page=page,
        limit=limit,
        sort_by=sortBy,
        sort_order=sortOrder,
    )
    agents = [AgentListResponse(**item) for item in agents_data]
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 0
    return create_success_response(
        data=AgentListPaginatedResponse(
            agents=agents,
            pagination=PaginationInfo(
                page=page,
                limit=limit,
                totalItems=total_items,
                totalPages=total_pages,
            ),
        ),
        message=None,
    )


@router.get("/invites", response_model=StandardResponse[List[dict]])
def list_invites(
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
    used: Optional[bool] = Query(None, description=ApiDocs.FILTER_BY_IS_USED),
) -> StandardResponse[List[dict]]:
    """Admin: List invites created by current admin."""
    data = service.list_invites(current_user, used=used)
    return create_success_response(data=data, message=None)


@router.get("/assignments", response_model=StandardResponse[List[AdminAgentAssignmentResponse]])
def get_assignments(
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
    agent_id: Optional[uuid.UUID] = Query(None, description=ApiDocs.FILTER_BY_AGENT_ID),
    admin_id: Optional[uuid.UUID] = Query(
        None,
        description=ApiDocs.FILTER_BY_ADMIN_ID_DEFAULTS_CURRENT_USER,
    ),
) -> StandardResponse[List[AdminAgentAssignmentResponse]]:
    """
    Get admin-agent assignments with detailed information.
    """
    data = service.get_assignments(
        agent_id=agent_id,
        admin_id=admin_id,
        current_user=current_user,
    )
    return create_success_response(
        data=[AdminAgentAssignmentResponse(**item) for item in data],
        message=None,
    )


@router.get("/{agent_id}", response_model=StandardResponse[AgentDetailResponse])
def get_agent_details(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentDetailResponse]:
    """Admin: Get agent details by ID."""
    data = service.get_agent_details(agent_id)
    return create_success_response(data=AgentDetailResponse(**data), message=None)


@router.patch("/{agent_id}/accept", response_model=StandardResponse[AgentAcceptResponse])
def accept_agent(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentAcceptResponse]:
    """Admin: Accept an agent (change status from PENDING_REVIEW to ACTIVE)."""
    data = service.accept_agent(agent_id, current_user)
    return create_success_response(
        data=AgentAcceptResponse(**data),
        message=SuccessMessages.AGENT_ACCEPTED,
    )


@router.patch("/{agent_id}/decline", response_model=StandardResponse[AgentDeclineResponse])
def decline_agent(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    payload: Optional[dict] = Body(None),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentDeclineResponse]:
    """Admin: Decline an agent (change status from PENDING_REVIEW to DECLINED)."""
    reason = (payload or {}).get("reason") or Defaults.AGENT_DECLINE_REASON_ADMIN
    data = service.decline_agent(agent_id, reason=reason, current_user=current_user)
    return create_success_response(
        data=AgentDeclineResponse(**data),
        message=SuccessMessages.AGENT_DECLINED,
    )


@router.patch(
    "/{agent_id}/status",
    response_model=StandardResponse[AgentStatusUpdateResponse],
)
def update_agent_status(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    payload: AgentStatusUpdateRequest = Body(...),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentStatusUpdateResponse]:
    """
    Admin: Update an agent's status (ACTIVE or INACTIVE) with optional reason.
    """
    data = service.update_agent_status(agent_id, payload, current_user)
    return create_success_response(
        data=AgentStatusUpdateResponse(**data),
        message=SuccessMessages.AGENT_STATUS_UPDATED,
    )


@router.delete("/{agent_id}", response_model=StandardResponse[AgentDeleteResponse])
def delete_agent(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentDeleteResponse]:
    """Admin: Soft delete an agent."""
    data = service.delete_agent(agent_id, current_user)
    return create_success_response(
        data=AgentDeleteResponse(**data),
        message=SuccessMessages.AGENT_DELETED,
    )


@router.post("/{agent_id}/resend-invite", response_model=StandardResponse[AgentInviteResponse])
def resend_invite(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentInviteResponse]:
    """Admin: Resend invitation email to an agent."""
    data = service.resend_invite(agent_id, current_user)
    return create_success_response(
        data=AgentInviteResponse(**data),
        message=SuccessMessages.INVITE_RESENT,
    )


@router.patch("/{agent_id}/revoke-invite", response_model=StandardResponse[dict])
def revoke_invite(
    agent_id: uuid.UUID = Path(..., description=ApiDocs.AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[dict]:
    """Admin: Revoke an invitation that was sent by mistake."""
    data = service.revoke_invite(agent_id, current_user)
    return create_success_response(
        data=data,
        message=SuccessMessages.INVITE_REVOKED,
    )


# ============================================================================
# Agent Endpoints (Public - No Auth Required)
# ============================================================================


@router.get("/invite/validate", response_model=StandardResponse[AgentValidateInviteResponse], include_in_schema=False)
def validate_invite_token_query(
    token: str = Query(..., description=ApiDocs.INVITE_TOKEN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentValidateInviteResponse]:
    """Compatibility endpoint for query-param token validation."""
    email, status, already_submitted, message = service.validate_invite_token(token)
    return create_success_response(
        data=AgentValidateInviteResponse(
            email=email,
            status=status,
            alreadySubmitted=already_submitted,
        ),
        message=message,
    )


@router.post("/onboarding", response_model=StandardResponse[AgentOnboardingFormResponse], include_in_schema=False)
def submit_onboarding_compat(
    payload: dict = Body(...),
    token: Optional[str] = Query(None, description=ApiDocs.INVITE_TOKEN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[AgentOnboardingFormResponse]:
    """Compatibility endpoint for clients posting onboarding payload to /onboarding."""
    resolved_token = token or payload.get("token")
    if not resolved_token:
        api_logger.warning(
            format_log_message(LogMessages.ApiRoutes.AGENTS_ONBOARDING_COMPAT_MISSING_TOKEN)
        )
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVITE_TOKEN_REQUIRED,
        )
    phone = payload.get("phone") or payload.get("phone_number")
    if isinstance(phone, str):
        phone = phone.strip()
        if phone.isdigit() and len(phone) == 10:
            phone = f"{Defaults.DEFAULT_PHONE_PREFIX_10_DIGIT}{phone}"
    try:
        form_data = AgentOnboardingFormRequest(
            fullName=payload.get("fullName") or payload.get("full_name"),
            phone=phone,
            serviceArea=payload.get("serviceArea") or payload.get("service_area"),
        )
    except ValidationError as e:
        sanitized_errors = _sanitize_validation_errors(e.errors())
        api_logger.warning(
            format_log_message(
                LogMessages.ApiRoutes.AGENTS_ONBOARDING_COMPAT_VALIDATION_FAILED,
                error_count=len(sanitized_errors),
            )
        )
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=sanitized_errors,
        ) from e
    data = service.submit_onboarding_form(resolved_token, form_data)
    return create_success_response(
        data=AgentOnboardingFormResponse(**data),
        message=SuccessMessages.AGENT_ONBOARDING_SUBMITTED_UNDER_REVIEW,
    )


# ============================================================================
# Admin-Agent Assignment Endpoints
# ============================================================================


@router.post("/assign-agent", response_model=StandardResponse[bool])
def assign_agent(
    assign_in: AdminAgentAssignmentRequest,
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[bool]:
    """
    Assign an agent to the current authenticated admin for permission inheritance.
    """
    service.assign_agent(assign_in, current_user)
    return create_success_response(data=True, message=SuccessMessages.AGENT_ASSIGNED)


@router.post("/unassign-agent", response_model=StandardResponse[bool])
def unassign_agent(
    unassign_in: AdminAgentAssignmentRequest,
    current_user: User = require_role(UserRoles.ADMIN),
    service: AgentService = Depends(get_agent_service),
) -> StandardResponse[bool]:
    """Revoke an agent's inherited admin privileges."""
    service.unassign_agent(unassign_in, current_user)
    return create_success_response(data=True, message=SuccessMessages.AGENT_REVOKED)
