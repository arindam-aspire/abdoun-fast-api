"""
Agent routes: invite, onboarding, admin CRUD, assignments.
All behaviour delegated to AgentService; no DB or business logic in this module.
"""

import json
import math
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import ValidationError

from app.api.v1.deps.agent_dashboard import get_agent_dashboard_service
from app.api.v1.deps.agents import get_agent_service
from app.api.v1.deps.security import get_current_user, require_role
from app.models.user import User
from app.schemas.user import (
    AgentDashboardSummaryResponse,
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
    AgentSummaryItem,
    AgentSummaryResponse,
    TopAgentLeaderboardItem,
    TopAgentsLeaderboardResponse,
    AgentOnboardingFormRequest,
    AgentOnboardingFormResponse,
    AgentStatusUpdateRequest,
    AgentStatusUpdateResponse,
    AgentValidateInviteResponse,
    PaginationInfo,
)
from app.services.agent_service import AgentService
from app.services.agent_dashboard_service import AgentDashboardService
from app.utils.constants import ApiDocs, Defaults, UserRoles
from app.utils.responses import StandardResponse, create_success_response
from app.utils.constants import ErrorMessages, SuccessMessages
from app.utils.status_codes import HTTPStatus
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger

router = APIRouter()


def _sanitize_ctx_value(value: object) -> object:
    """Return a JSON-serializable version of a Pydantic error ctx value."""
    if isinstance(value, BaseException):
        return str(value)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


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
            clean["ctx"] = {key: _sanitize_ctx_value(value) for key, value in ctx.items()}
        sanitized.append(clean)
    return sanitized


# ============================================================================
# Admin Endpoints
# ============================================================================


@router.post("/invite")
def invite_agent(
    invite_in: AgentInviteRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
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


@router.post("/manual-onboard")
def create_agent_direct(
    body: AdminCreateAgentRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AdminCreateAgentResponse]:
    """
    Admin: directly create an agent (no invite flow) with a temporary password.
    """
    data = service.create_agent_direct(body, current_user)
    return create_success_response(
        data=AdminCreateAgentResponse(**data),
        message=SuccessMessages.AGENT_CREATED_WITH_TEMP_PASSWORD,
    )


@router.get("")
def list_agents(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
    status: Annotated[Optional[str], Query(description=ApiDocs.FILTER_BY_STATUS)] = None,
    search: Annotated[Optional[str], Query(description=ApiDocs.SEARCH_BY_NAME_OR_EMAIL)] = None,
    page: Annotated[int, Query(ge=1, description=ApiDocs.PAGE_NUMBER)] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description=ApiDocs.ITEMS_PER_PAGE)] = 20,
    sort_by: Annotated[str, Query(alias="sortBy", description=ApiDocs.SORT_FIELD)] = "invitedAt",
    sort_order: Annotated[str, Query(alias="sortOrder", description=ApiDocs.SORT_ORDER)] = "desc",
) -> StandardResponse[AgentListPaginatedResponse]:
    """Admin: List agents with pagination and filtering."""
    agents_data, total_items = service.list_agents(
        status=status,
        search=search,
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
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


@router.get("/summary")
def get_agents_summary(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentSummaryResponse]:
    """Admin: consolidated summary for all non-deleted agents (profile status, assignments, latest invite).

    ``profileStatus`` is the raw ``agent_profiles.status`` string. Each assignment includes stored
    ``isActive`` / ``revokedAt`` plus ``assignmentStatus`` (same labels as GET /agents/assignments).
    Top-level counts use stored profile status: ``pendingInvites`` (``INVITED``), ``pendingReview``
    (``PENDING_REVIEW``), ``declined`` (``DECLINED``), ``activeAgents`` (``ACTIVE``). ``lastFiveAgents``
    are up to five agents with the newest ``users.created_at`` (full detail per agent). There is no
    full ``agents`` list on this endpoint.

    **Sample request:** ``GET /api/v1/agents/summary`` with ``Authorization: Bearer <token>`` (admin).

    **Sample success JSON:**

    .. code-block:: json

        {
          "success": true,
          "data": {
            "totalAgents": 1,
            "activeAgents": 1,
            "pendingInvites": 0,
            "pendingReview": 0,
            "declined": 0,
            "lastFiveAgents": []
          },
          "message": null
        }
    """
    payload = service.get_agents_summary()
    return create_success_response(
        data=AgentSummaryResponse(
            totalAgents=payload["totalAgents"],
            activeAgents=payload["activeAgents"],
            pendingInvites=payload["pendingInvites"],
            pendingReview=payload["pendingReview"],
            declined=payload["declined"],
            lastFiveAgents=[AgentSummaryItem(**row) for row in payload["lastFiveAgents"]],
        ),
        message=None,
    )


@router.get("/leaderboard")
def get_agents_leaderboard(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[TopAgentsLeaderboardResponse]:
    """Admin: **top 3 agents** over the **last 30 days UTC**.

    **Window:** ``lastDate`` = current time (UTC); ``firstDate`` = 30 days before ``lastDate`` (inclusive range for metrics).

    **Ranking:** (1) **closed deals** — primary; (2) **inquiry response rate** — secondary.

    **Metrics**

    - ``closedDeals``: listings with ``deal_closed`` whose ``updated_at`` falls in the window (inclusive).
    - ``responseRate``: among inquiries with ``leads.created_at`` in the window, percentage where
      ``updated_at > created_at``.
    - ``area``: ``agent_profiles.service_area`` (nullable).

    **Example:** ``GET /api/v1/agents/leaderboard``

    **Example ``data.agents`` item:**

    .. code-block:: json

        {
          "name": "Omar Shdeifat",
          "closedDeals": 19,
          "responseRate": "94%",
          "area": "Dabouq"
        }
    """
    payload = service.get_top_agents_leaderboard()
    return create_success_response(
        data=TopAgentsLeaderboardResponse(
            firstDate=payload["firstDate"],
            lastDate=payload["lastDate"],
            agents=[TopAgentLeaderboardItem(**a) for a in payload["agents"]],
        ),
        message=None,
    )


@router.get("/invites")
def list_invites(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
    used: Annotated[Optional[bool], Query(description=ApiDocs.FILTER_BY_IS_USED)] = None,
) -> StandardResponse[List[dict]]:
    """Admin: List invites created by current admin."""
    data = service.list_invites(current_user, used=used)
    return create_success_response(data=data, message=None)


@router.get("/assignments")
def get_assignments(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
    agent_id: Annotated[Optional[uuid.UUID], Query(description=ApiDocs.FILTER_BY_AGENT_ID)] = None,
    admin_id: Annotated[
        Optional[uuid.UUID],
        Query(description=ApiDocs.FILTER_BY_ADMIN_ID_DEFAULTS_CURRENT_USER),
    ] = None,
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


@router.get("/dashboard/summary")
def get_dashboard_summary(
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[AgentDashboardService, Depends(get_agent_dashboard_service)],
) -> StandardResponse[AgentDashboardSummaryResponse]:
    """Return dashboard summary for the authenticated agent (own listings and metrics)."""
    data = service.get_dashboard_summary(current_user)
    return create_success_response(data=AgentDashboardSummaryResponse(**data), message=None)


@router.get("/{agent_id}")
def get_agent_details(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentDetailResponse]:
    """Admin: Get agent details by ID."""
    data = service.get_agent_details(agent_id)
    return create_success_response(data=AgentDetailResponse(**data), message=None)


@router.patch("/{agent_id}/accept")
def accept_agent(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentAcceptResponse]:
    """Admin: Accept an agent (change status from PENDING_REVIEW to ACTIVE)."""
    data = service.accept_agent(agent_id, current_user)
    return create_success_response(
        data=AgentAcceptResponse(**data),
        message=SuccessMessages.AGENT_ACCEPTED,
    )


@router.patch("/{agent_id}/decline")
def decline_agent(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
    payload: Annotated[Optional[dict], Body()] = None,
) -> StandardResponse[AgentDeclineResponse]:
    """Admin: Decline an agent (change status from PENDING_REVIEW to DECLINED)."""
    reason = (payload or {}).get("reason") or Defaults.AGENT_DECLINE_REASON_ADMIN
    data = service.decline_agent(agent_id, reason=reason, current_user=current_user)
    return create_success_response(
        data=AgentDeclineResponse(**data),
        message=SuccessMessages.AGENT_DECLINED,
    )


@router.patch("/{agent_id}/status")
def update_agent_status(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    payload: Annotated[AgentStatusUpdateRequest, Body()],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentStatusUpdateResponse]:
    """
    Admin: Update an agent's status (ACTIVE or INACTIVE) with optional reason.
    """
    data = service.update_agent_status(agent_id, payload, current_user)
    return create_success_response(
        data=AgentStatusUpdateResponse(**data),
        message=SuccessMessages.AGENT_STATUS_UPDATED,
    )


@router.delete("/{agent_id}")
def delete_agent(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentDeleteResponse]:
    """Admin: Soft delete an agent."""
    data = service.delete_agent(agent_id, current_user)
    return create_success_response(
        data=AgentDeleteResponse(**data),
        message=SuccessMessages.AGENT_DELETED,
    )


@router.post("/{agent_id}/resend-invite")
def resend_invite(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentInviteResponse]:
    """Admin: Resend invitation email to an agent."""
    data = service.resend_invite(agent_id, current_user)
    return create_success_response(
        data=AgentInviteResponse(**data),
        message=SuccessMessages.INVITE_RESENT,
    )


@router.post("/{agent_id}/resend-invitation")
def resend_invitation(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[AgentInviteResponse]:
    """Admin: Resend invitation email to an agent (compat endpoint)."""
    data = service.resend_invite(agent_id, current_user)
    return create_success_response(
        data=AgentInviteResponse(**data),
        message=SuccessMessages.INVITE_RESENT,
    )


@router.patch("/{agent_id}/revoke-invite")
def revoke_invite(
    agent_id: Annotated[uuid.UUID, Path(description=ApiDocs.AGENT_ID_DESC)],
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
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


@router.get("/invite/validate", include_in_schema=False)
def validate_invite_token_query(
    token: Annotated[str, Query(description=ApiDocs.INVITE_TOKEN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
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


@router.post("/onboarding", include_in_schema=False)
def submit_onboarding_compat(
    payload: Annotated[dict, Body()],
    service: Annotated[AgentService, Depends(get_agent_service)],
    token: Annotated[Optional[str], Query(description=ApiDocs.INVITE_TOKEN)] = None,
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


@router.post("/assign-agent")
def assign_agent(
    assign_in: AdminAgentAssignmentRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[bool]:
    """
    Assign an agent to the current authenticated admin for permission inheritance.
    """
    service.assign_agent(assign_in, current_user)
    return create_success_response(data=True, message=SuccessMessages.AGENT_ASSIGNED)


@router.post("/unassign-agent")
def unassign_agent(
    unassign_in: AdminAgentAssignmentRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StandardResponse[bool]:
    """Revoke an agent's inherited admin privileges."""
    service.unassign_agent(unassign_in, current_user)
    return create_success_response(data=True, message=SuccessMessages.AGENT_REVOKED)
