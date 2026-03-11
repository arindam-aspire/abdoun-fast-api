import secrets
import uuid
import math
import json
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, and_, or_, func

from app.db.session import get_db
from app.core.config import get_settings
from app.core.auth import get_current_user
from app.core.permissions import require_role, require_permission
from app.models.user import User, Role, AgentInvite, AgentProfile, AdminAgentAssignment
from app.schemas.user import (
    AgentInviteRequest,
    AdminAgentAssignmentRequest,
    AdminAgentAssignmentResponse,
    AgentOnboardingFormRequest,
    AgentOnboardingFormResponse,
    AgentValidateInviteResponse,
    AgentListResponse,
    AgentDetailResponse,
    AgentInviteResponse,
    AgentAcceptRequest,
    AgentAcceptResponse,
    AgentDeclineResponse,
    AgentDeleteResponse,
    AgentListPaginatedResponse,
    PaginationInfo,
    AgentStatusUpdateRequest,
    AgentStatusUpdateResponse,
)
from app.utils.responses import StandardResponse, create_success_response
from app.utils.constants import SuccessMessages, ErrorMessages, InfoMessages, UserRoles, UserPermissions, AgentStatus
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger
from app.services.notification import notify_agent_approved, notify_agent_rejected, notify_agent_invite_sent
from app.services.cognito import cognito_service
from botocore.exceptions import NoCredentialsError

router = APIRouter()


# ============================================================================
# Admin Endpoints
# ============================================================================
AGENT_ID_DESC = "Agent ID"


def _get_missing_cognito_config(settings) -> List[str]:
    missing_config = []
    if not settings.cognito_user_pool_id or not settings.cognito_user_pool_id.strip():
        missing_config.append("COGNITO_USER_POOL_ID")
    if not settings.cognito_client_id or not settings.cognito_client_id.strip():
        missing_config.append("COGNITO_APP_CLIENT_ID")
    return missing_config


def _try_create_cognito_user_for_agent(
    user: User,
    current_user: User,
    agent_id: uuid.UUID,
    settings,
) -> None:
    # Create user in Cognito if configured and not already created
    # DO NOT overwrite existing cognito_sub if already set
    if user.cognito_sub:
        api_logger.info(
            f"Agent {agent_id} already has cognito_sub: {user.cognito_sub}. Skipping Cognito user creation."
        )
        return

    pool_id = (settings.cognito_user_pool_id or "").strip()
    client_id = (settings.cognito_client_id or "").strip()
    cognito_enabled = bool(pool_id and client_id)
    if not cognito_enabled:
        missing_config = _get_missing_cognito_config(settings)
        api_logger.warning(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="cognito create user skipped (missing config)",
                error=f"user_id={user.id}, missing={', '.join(missing_config) if missing_config else 'unknown'}",
            )
            + " - Agent approval will proceed but Cognito user not created. Set missing values in .env to enable Cognito user creation."
        )
        return

    try:
        cognito_response = cognito_service.create_agent_user(
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number,
        )
        # Store cognito_sub from Cognito response
        # The Username field in the response is the cognito_sub
        if cognito_response and "User" in cognito_response:
            cognito_sub = cognito_response["User"]["Username"]
            user.cognito_sub = cognito_sub
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_APPROVED,
                    agent_id=str(agent_id),
                    approver_id=current_user.email,
                )
                + f" | Cognito user created with sub: {cognito_sub}"
            )
        else:
            api_logger.warning(
                format_log_message(
                    LogMessages.RBAC.NOTIFICATION_FAILED,
                    context="cognito create user - invalid response",
                    error=f"user_id={user.id}, email={user.email}",
                )
            )
    except NoCredentialsError as cred_error:
        # AWS credentials not configured - allow agent approval to proceed
        # The agent can still be approved, but they won't be able to login until Cognito user is created
        api_logger.warning(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="cognito create user - AWS credentials not configured",
                error=f"user_id={user.id}, email={user.email}, error={str(cred_error)}",
            )
            + " - Agent approval will proceed but Cognito user not created"
        )
    except Exception as cognito_error:
        # Other Cognito errors - log but allow approval to proceed
        # The agent can still be approved, but they won't be able to login until Cognito user is created
        api_logger.error(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="cognito create user failed",
                error=f"user_id={user.id}, email={user.email}, error={str(cognito_error)}",
            )
            + " - Agent approval will proceed but Cognito user not created"
        )
def _apply_agent_filters(stmt, status: Optional[str], search: Optional[str]):
    if status:
        stmt = stmt.where(AgentProfile.status == status)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern),
            )
        )
    return stmt


def _get_agent_order_column(sort_by: str):
    if sort_by == "invitedAt":
        return AgentProfile.form_submitted_at if hasattr(AgentProfile, "form_submitted_at") else User.created_at
    if sort_by == "email":
        return User.email
    if sort_by == "fullName":
        return User.full_name
    return User.created_at


def _apply_sort(stmt, order_col, sort_order: str):
    if sort_order.lower() == "asc":
        return stmt.order_by(order_col.asc())
    return stmt.order_by(order_col.desc())


def _get_latest_invite_info(db: Session, email: str):
    stmt_invite = (
        select(AgentInvite, User.full_name)
        .outerjoin(User, User.id == AgentInvite.invited_by)
        .where(AgentInvite.email == email)
        .order_by(AgentInvite.created_at.desc())
    )
    invite_result = db.execute(stmt_invite).first()
    if not invite_result:
        return None, None
    return invite_result[0], invite_result[1]


def _get_agent_with_profile(db: Session, agent_id: uuid.UUID):
    stmt = (
        select(User, AgentProfile)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(
            and_(
                User.id == agent_id,
                AgentProfile.deleted_at.is_(None),
            )
        )
    )
    result = db.execute(stmt).first()
    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.AGENT_NOT_FOUND,
        )
    return result


def _ensure_pending_review(profile: AgentProfile) -> None:
    if profile.status != AgentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_STATUS_TRANSITION,
        )


def _approve_agent(profile: AgentProfile, user: User, current_user: User) -> None:
    profile.status = AgentStatus.ACTIVE
    profile.reviewed_at = datetime.now()
    profile.reviewed_by = current_user.id
    profile.approved_by = current_user.id
    profile.approved_at = datetime.now()
    user.is_active = True


def _notify_agent_approved_safely(user: User) -> None:
    try:
        notify_agent_approved(user.email, user.full_name)
    except Exception as n:
        api_logger.warning(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="agent approved",
                error=str(n),
            )
        )


def _sanitize_validation_errors(errors: List[dict]) -> List[dict]:
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


@router.post("/invite", response_model=StandardResponse[AgentInviteResponse])
def invite_agent(
    invite_in: AgentInviteRequest,
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db)
):
    """
    Admin: Invite an agent.
    Creates an AgentInvite record and sends an invite email.
    """
    # Check if user already exists in the database (regardless of role)
    stmt_user = select(User).where(User.email == invite_in.email)
    existing_user = db.execute(stmt_user).scalar_one_or_none()
    
    if existing_user:
        # If user exists and already has an agent profile, they're already an agent
        if existing_user.profile:
            api_logger.warning(format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=invite_in.email))
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.AGENT_ALREADY_EXISTS
            )
        # If user exists but doesn't have agent profile, prevent sending invitation
        # Admin should assign agent role directly instead of sending invitation
        else:
            api_logger.warning(format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=invite_in.email))
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_EXISTS
            )
    
    # Check for existing unused invite
    stmt_invite = select(AgentInvite).where(
        and_(
            AgentInvite.email == invite_in.email,
            AgentInvite.is_used == False,
            AgentInvite.expires_at > datetime.now()
        )
    )
    existing_invite = db.execute(stmt_invite).scalar_one_or_none()
    if existing_invite:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=ErrorMessages.AGENT_ALREADY_EXISTS
        )
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)
    
    db_invite = AgentInvite(
        email=invite_in.email,
        invited_by=current_user.id,
        token=token,
        expires_at=expires_at,
        invited_at=datetime.now()
    )
    db.add(db_invite)
    
    try:
        db.commit()
        db.refresh(db_invite)
        
        settings = get_settings()
        # Generate invite link with locale (defaulting to 'en' for now)
        invite_link = f"{settings.app_base_url.rstrip('/')}/en/agent-invite?token={token}"
        
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_INVITED, email=invite_in.email, invited_by=current_user.email))
        
        try:
            notify_agent_invite_sent(invite_in.email, invite_link, current_user.email)
        except Exception as n:
            api_logger.warning(format_log_message(LogMessages.RBAC.NOTIFICATION_FAILED, context="agent invite", error=str(n)))
        
        # Create User + AgentProfile with INVITED status (user doesn't exist at this point)
        # `users.phone_number` is unique/non-null; use the agreed placeholder
        # until onboarding form submission provides the real number.
        placeholder_phone = "+00 000000000"
        db_user = User(
            email=invite_in.email,
            full_name="",  # Will be filled when form is submitted
            phone_number=placeholder_phone,
            is_active=False
        )
        db.add(db_user)
        db.flush()
        
        # Assign Agent role
        stmt_role = select(Role).where(Role.name == UserRoles.AGENT)
        role = db.execute(stmt_role).scalar_one_or_none()
        if role:
            db_user.roles.append(role)
        
        # Create AgentProfile with INVITED status
        db_profile = AgentProfile(
            user_id=db_user.id,
            status=AgentStatus.INVITED
        )
        db.add(db_profile)
        db.commit()
        db.refresh(db_user)
        db.refresh(db_profile)
        
        return create_success_response(
            data=AgentInviteResponse(
                id=db_user.id,  # Use user ID, not invite ID
                email=db_invite.email,
                status=AgentStatus.INVITED,
                inviteLink=invite_link,
                invitedAt=db_invite.invited_at or db_invite.created_at,
                invitedBy=current_user.full_name
            ),
            message=f"Invitation sent to {invite_in.email}"
        )
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e)))
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ErrorMessages.INVITE_FAILED
        )


@router.get("", response_model=StandardResponse[AgentListPaginatedResponse])
def list_agents(
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sortBy: str = Query("invitedAt", description="Sort field"),
    sortOrder: str = Query("desc", description="Sort order (asc/desc)")
):
    """
    Admin: List agents with pagination and filtering.
    """
    # Build base query - join User and AgentProfile, exclude soft-deleted
    stmt = (
        select(User, AgentProfile)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(AgentProfile.deleted_at.is_(None))
    )
    
    stmt = _apply_agent_filters(stmt, status, search)
    
    # Get total count before pagination
    # Create a count query
    count_query = (
        select(func.count(User.id))
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(AgentProfile.deleted_at.is_(None))
    )
    count_query = _apply_agent_filters(count_query, status, search)
    total_items = db.execute(count_query).scalar() or 0
    
    # Apply sorting
    order_col = _get_agent_order_column(sortBy)
    stmt = _apply_sort(stmt, order_col, sortOrder)
    
    # Apply pagination
    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)
    
    results = db.execute(stmt).all()
    
    agents = []
    for user, profile in results:
        # Get invite info
        invite, inviter_name = _get_latest_invite_info(db, user.email)
        
        agents.append(AgentListResponse(
            id=user.id,
            email=user.email,
            fullName=user.full_name if user.full_name else None,
            phone=user.phone_number if user.phone_number else None,
            serviceArea=profile.service_area,
            status=profile.status,
            invitedAt=invite.created_at if invite else None,
            invitedBy=inviter_name if invite else None,
            formSubmittedAt=profile.form_submitted_at,
            reviewedAt=profile.reviewed_at,
            declineReason=profile.decline_reason
        ))
    
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 0
    
    return create_success_response(
        data=AgentListPaginatedResponse(
            agents=agents,
            pagination=PaginationInfo(
                page=page,
                limit=limit,
                totalItems=total_items,
                totalPages=total_pages
            )
        )
    )


@router.get("/invites", response_model=StandardResponse[List[dict]])
def list_invites(
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db),
    used: Optional[bool] = Query(None, description="Filter by is_used: true/false"),
):
    """Admin: List invites created by current admin."""
    stmt = select(AgentInvite).where(AgentInvite.invited_by == current_user.id)
    if used is not None:
        stmt = stmt.where(AgentInvite.is_used == used)
    stmt = stmt.order_by(AgentInvite.created_at.desc())
    invites = db.execute(stmt).scalars().all()

    # Resolve current agent status by invited email in one query.
    emails = [inv.email for inv in invites if inv.email]
    status_by_email = {}
    if emails:
        status_rows = db.execute(
            select(User.email, AgentProfile.status)
            .join(AgentProfile, User.id == AgentProfile.user_id)
            .where(User.email.in_(emails))
        ).all()
        status_by_email = {email: status for email, status in status_rows}

    data = [
        {
            "id": str(inv.id),
            "email": inv.email,
            "expires_at": inv.expires_at,
            "is_used": inv.is_used,
            "created_at": inv.created_at,
            "status": status_by_email.get(inv.email, AgentStatus.INVITED),
        }
        for inv in invites
    ]
    return create_success_response(data=data, message=None)

@router.get("/assignments", response_model=StandardResponse[List[AdminAgentAssignmentResponse]])
def get_assignments(
    agent_id: Optional[uuid.UUID] = Query(None, description="Filter by agent ID"),
    admin_id: Optional[uuid.UUID] = Query(None, description="Filter by admin ID (defaults to current user)"),
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db)
):
    """
    Get admin-agent assignments with detailed information.
    
    - If agent_id is provided: Returns all assignments for that agent
    - If admin_id is provided: Returns all assignments for that admin (defaults to current user)
    - If neither is provided: Returns all assignments for the current admin
    """
    # Default to current user's admin_id if not specified
    if admin_id is None:
        admin_id = current_user.id
    
    # Build query
    stmt = select(AdminAgentAssignment)
    
    # Apply filters
    conditions = []
    if agent_id:
        conditions.append(AdminAgentAssignment.agent_id == agent_id)
    if admin_id:
        conditions.append(AdminAgentAssignment.admin_id == admin_id)
    
    if conditions:
        stmt = stmt.where(and_(*conditions))
    
    # Order by assigned_at descending
    stmt = stmt.order_by(AdminAgentAssignment.assigned_at.desc())
    
    assignments_db = db.execute(stmt).scalars().all()
    
    # Build response with user details
    assignments = []
    for assignment in assignments_db:
        # Load admin and agent users
        admin_user = assignment.admin
        agent_user = assignment.agent
        
        # Determine status (plain text, no symbols)
        if assignment.is_active and assignment.revoked_at is None:
            status = "ACTIVE"
        else:
            status = "INACTIVE/REVOKED"
        
        assignments.append(AdminAgentAssignmentResponse(
            id=assignment.id,
            admin_id=assignment.admin_id,
            admin_email=admin_user.email,
            admin_name=admin_user.full_name,
            agent_id=assignment.agent_id,
            agent_email=agent_user.email,
            agent_name=agent_user.full_name,
            is_active=assignment.is_active,
            can_inherit_privileges=assignment.can_inherit_privileges,
            assigned_at=assignment.assigned_at,
            revoked_at=assignment.revoked_at,
            status=status
        ))
    
    return create_success_response(data=assignments, message=None)





@router.get("/{agent_id}", response_model=StandardResponse[AgentDetailResponse])
def get_agent_details(
    agent_id: uuid.UUID = Path(..., description=AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db)
):
    """
    Admin: Get agent details by ID.
    """
    stmt = (
        select(User, AgentProfile)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(
            and_(
                User.id == agent_id,
                AgentProfile.deleted_at.is_(None)
            )
        )
    )
    result = db.execute(stmt).first()
    
    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.AGENT_NOT_FOUND
        )
    
    user, profile = result
    
    # Get invite info
    stmt_invite = (
        select(AgentInvite, User.full_name)
        .outerjoin(User, User.id == AgentInvite.invited_by)
        .where(AgentInvite.email == user.email)
        .order_by(AgentInvite.created_at.desc())
    )
    invite_result = db.execute(stmt_invite).first()
    invite = invite_result[0] if invite_result else None
    inviter_name = invite_result[1] if invite_result else None
    
    return create_success_response(
        data=AgentDetailResponse(
            id=user.id,
            email=user.email,
            fullName=user.full_name if user.full_name else None,
            phone=user.phone_number if user.phone_number else None,
            serviceArea=profile.service_area,
            status=profile.status,
            invitedAt=invite.created_at if invite else None,
            invitedBy=inviter_name if invite else None,
            formSubmittedAt=profile.form_submitted_at,
            reviewedAt=profile.reviewed_at,
            reviewedBy=profile.reviewed_by,
            declineReason=profile.decline_reason,
            passwordSetAt=profile.password_set_at
        )
    )


@router.patch("/{agent_id}/accept", response_model=StandardResponse[AgentAcceptResponse])
def accept_agent(
    agent_id: uuid.UUID = Path(..., description=AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db)
):
    """
    Admin: Accept an agent (change status from PENDING_REVIEW to ACTIVE).
    """
    user, profile = _get_agent_with_profile(db, agent_id)
    _ensure_pending_review(profile)
    
    try:
        settings = get_settings()
        _try_create_cognito_user_for_agent(user, current_user, agent_id, settings)
        
        # Update status to ACTIVE
        _approve_agent(profile, user, current_user)
        
        db.commit()
        
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_APPROVED, agent_id=str(agent_id), approver_id=current_user.email))
        
        _notify_agent_approved_safely(user)
        
        return create_success_response(
            data=AgentAcceptResponse(
                id=user.id,
                status=profile.status,
                reviewedAt=profile.reviewed_at,
                reviewedBy=profile.reviewed_by
            ),
            message=SuccessMessages.AGENT_ACCEPTED
        )
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.APPROVAL_FAILED_LOG, agent_id=str(agent_id), error=str(e)))
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ErrorMessages.APPROVAL_FAILED
        )


@router.patch("/{agent_id}/decline", response_model=StandardResponse[AgentDeclineResponse])
def decline_agent(
    agent_id: uuid.UUID = Path(..., description=AGENT_ID_DESC),
    payload: Optional[dict] = Body(None),
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db)
):
    """
    Admin: Decline an agent (change status from PENDING_REVIEW to DECLINED).
    """
    reason = (payload or {}).get("reason") or "Application rejected by admin"
    
    stmt = (
        select(User, AgentProfile)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(
            and_(
                User.id == agent_id,
                AgentProfile.deleted_at.is_(None)
            )
        )
    )
    result = db.execute(stmt).first()
    
    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.AGENT_NOT_FOUND
        )
    
    user, profile = result
    
    if profile.status != AgentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_STATUS_TRANSITION
        )
    
    try:
        profile.status = AgentStatus.DECLINED
        profile.decline_reason = reason
        profile.reviewed_at = datetime.now()
        profile.reviewed_by = current_user.id
        
        db.commit()
        
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_REJECTED, agent_id=str(agent_id), rejector_id=current_user.email))
        
        try:
            notify_agent_rejected(user.email, user.full_name, profile.decline_reason)
        except Exception as n:
            api_logger.warning(format_log_message(LogMessages.RBAC.NOTIFICATION_FAILED, context="agent rejected", error=str(n)))
        
        return create_success_response(
            data=AgentDeclineResponse(
                id=user.id,
                status=profile.status,
                declineReason=profile.decline_reason,
                reviewedAt=profile.reviewed_at,
                reviewedBy=profile.reviewed_by
            ),
            message=SuccessMessages.AGENT_DECLINED
        )
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.AGENT_REJECT_FAILED_LOG, agent_id=str(agent_id), error=str(e)))
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ErrorMessages.AGENT_REJECT_FAILED
        )


@router.patch(
    "/{agent_id}/status",
    response_model=StandardResponse[AgentStatusUpdateResponse],
)
def update_agent_status(
    agent_id: uuid.UUID = Path(..., description=AGENT_ID_DESC),
    payload: AgentStatusUpdateRequest = Body(...),
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db),
):
    """
    Admin: Update an agent's status (ACTIVE or INACTIVE) with optional reason.

    - When setting status to INACTIVE, the agent will not be able to perform any actions
      (their `User.is_active` flag is set to False).
    - Only an admin can change this back to ACTIVE; agents cannot self-activate.
    """
    target_status = payload.status
    reason = payload.reason

    allowed_statuses = {AgentStatus.ACTIVE, AgentStatus.INACTIVE}
    if target_status not in allowed_statuses:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_AGENT_STATUS,
        )

    stmt = (
        select(User, AgentProfile)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(User.id == agent_id)
    )
    result = db.execute(stmt).first()

    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.AGENT_NOT_FOUND,
        )

    user, profile = result

    if profile.deleted_at is not None or profile.status == AgentStatus.DELETED:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.ALREADY_DELETED,
        )

    # Enforce valid transitions
    current_status = profile.status
    if current_status == AgentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_AGENT_STATUS_TRANSITION,
        )

    try:
        if target_status == AgentStatus.INACTIVE:
            profile.status = AgentStatus.INACTIVE
            profile.status_reason = reason
            user.is_active = False
        elif target_status == AgentStatus.ACTIVE:
            profile.status = AgentStatus.ACTIVE
            profile.status_reason = reason
            user.is_active = True

        db.commit()
        db.refresh(user)
        db.refresh(profile)

        return create_success_response(
            data=AgentStatusUpdateResponse(
                id=user.id,
                status=profile.status,
                statusReason=profile.status_reason,
            ),
            message=SuccessMessages.AGENT_STATUS_UPDATED,
        )
    except Exception as e:
        db.rollback()
        api_logger.error(
            format_log_message(
                LogMessages.RBAC.AGENT_STATUS_UPDATE_FAILED,
                agent_id=str(agent_id),
                error=str(e),
            )
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ErrorMessages.INTERNAL_SERVER_ERROR,
        )


@router.delete("/{agent_id}", response_model=StandardResponse[AgentDeleteResponse])
def delete_agent(
    agent_id: uuid.UUID = Path(..., description=AGENT_ID_DESC),
    current_user: User = require_role(UserRoles.ADMIN),
    db: Session = Depends(get_db)
):
    """
    Admin: Soft delete an agent.
    """
    stmt = (
        select(User, AgentProfile)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(User.id == agent_id)
    )
    result = db.execute(stmt).first()
    
    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.AGENT_NOT_FOUND
        )
    
    user, profile = result
    
    if profile.deleted_at is not None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.ALREADY_DELETED
        )
    
    try:
        profile.deleted_at = datetime.now()
        profile.deleted_by = current_user.id
        profile.status = AgentStatus.DELETED  # Set status to DELETED
        user.is_active = False
        
        db.commit()
        
        api_logger.info(format_log_message(LogMessages.RBAC.USER_DELETED_LOG, user_id=str(agent_id), admin_email=current_user.email))
        
        return create_success_response(
            data=AgentDeleteResponse(
                id=user.id,
                status=profile.status,
                deletedAt=profile.deleted_at,
                deletedBy=profile.deleted_by
            ),
            message=SuccessMessages.AGENT_DELETED
        )
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.USER_DELETE_FAILED_LOG, error=str(e)))
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ErrorMessages.INTERNAL_SERVER_ERROR
        )


# ============================================================================
# Agent Endpoints (Public - No Auth Required)
# ============================================================================

@router.get("/invite/validate", response_model=StandardResponse[AgentValidateInviteResponse], include_in_schema=False)
def validate_invite_token_query(
    token: str = Query(..., description="Invite token"),
    db: Session = Depends(get_db)
):
    """Compatibility endpoint for query-param token validation."""
    return _validate_invite_token(token, db)


def _validate_invite_token(
    token: str,
    db: Session
):
    """
    Shared invite-token validation logic for public/legacy routes.
    """
    stmt = select(AgentInvite).where(
        and_(
            AgentInvite.token == token,
            AgentInvite.expires_at > datetime.now()
        )
    )
    invite = db.execute(stmt).scalar_one_or_none()
    
    if not invite:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.INVITE_NOT_FOUND
        )
    
    # Check if user exists and has profile
    stmt_user = select(User).where(User.email == invite.email)
    user = db.execute(stmt_user).scalar_one_or_none()
    
    already_submitted = False
    status = AgentStatus.INVITED
    
    if user and user.profile:
        status = user.profile.status
        already_submitted = user.profile.form_submitted_at is not None
    
    message = None
    if already_submitted:
        message = InfoMessages.AGENT_ALREADY_SUBMITTED
    
    return create_success_response(
        data=AgentValidateInviteResponse(
            email=invite.email,
            status=status,
            alreadySubmitted=already_submitted
        ),
        message=message
    )


def _submit_onboarding_form(
    token: str,
    form_data: AgentOnboardingFormRequest,
    db: Session
):
    """
    Agent: Submit onboarding form (public endpoint - token authenticates).
    """
    
    # Validate token
    stmt_invite = select(AgentInvite).where(
        and_(
            AgentInvite.token == token,
            AgentInvite.expires_at > datetime.now()
        )
    )
    invite = db.execute(stmt_invite).scalar_one_or_none()
    
    if not invite:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.INVITE_NOT_FOUND
        )
    
    # Get or create user
    stmt_user = select(User).where(User.email == invite.email)
    user = db.execute(stmt_user).scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="User not found for this invite"
        )
    
    # Check if already submitted
    if user.profile and user.profile.form_submitted_at:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=ErrorMessages.ALREADY_SUBMITTED
        )
    
    try:
        # Update user info
        user.full_name = form_data.fullName
        user.phone_number = form_data.phone
        
        # Update or create profile
        if not user.profile:
            profile = AgentProfile(
                user_id=user.id,
                service_area=form_data.serviceArea,
                status=AgentStatus.PENDING_REVIEW,
                form_submitted_at=datetime.now()
            )
            db.add(profile)
            db.flush()
        else:
            user.profile.service_area = form_data.serviceArea
            user.profile.status = AgentStatus.PENDING_REVIEW
            user.profile.form_submitted_at = datetime.now()
        
        # Mark invite as used
        invite.is_used = True
        
        db.commit()
        db.refresh(user)
        if user.profile:
            db.refresh(user.profile)
        
        api_logger.info(format_log_message(LogMessages.RBAC.REGISTRATION_PENDING, email=user.email))
        
        return create_success_response(
            data=AgentOnboardingFormResponse(
                email=user.email,
                status=user.profile.status if user.profile else AgentStatus.PENDING_REVIEW,
                formSubmittedAt=user.profile.form_submitted_at if user.profile else datetime.now()
            ),
            message="Your application has been submitted and is under review."
        )
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.REGISTRATION_FAILED_LOG, error=str(e)))
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.REGISTRATION_FAILED
        )


@router.post("/onboarding", response_model=StandardResponse[AgentOnboardingFormResponse], include_in_schema=False)
def submit_onboarding_compat(
    payload: dict = Body(...),
    token: Optional[str] = Query(None, description="Invite token"),
    db: Session = Depends(get_db),
):
    """Compatibility endpoint for clients posting onboarding payload to /onboarding."""
    resolved_token = token or payload.get("token")
    if not resolved_token:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Invite token is required"
        )

    phone = payload.get("phone") or payload.get("phone_number")
    if isinstance(phone, str):
        phone = phone.strip()
        if phone.isdigit() and len(phone) == 10:
            phone = f"+91{phone}"

    try:
        form_data = AgentOnboardingFormRequest(
            fullName=payload.get("fullName") or payload.get("full_name"),
            phone=phone,
            serviceArea=payload.get("serviceArea") or payload.get("service_area"),
        )
    except ValidationError as e:
        sanitized_errors = _sanitize_validation_errors(e.errors())
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=sanitized_errors) from e
    return _submit_onboarding_form(resolved_token, form_data, db)


# ============================================================================
# Legacy Endpoints (for backward compatibility)
# ============================================================================

# ============================================================================
# Admin-Agent Assignment Endpoints
# ============================================================================

@router.post("/assign-agent", response_model=StandardResponse[bool])
def assign_agent(assign_in: AdminAgentAssignmentRequest, current_user: User = require_role(UserRoles.ADMIN), db: Session = Depends(get_db)):
    """
    Assign an agent to the current authenticated admin for permission inheritance.
    
    The admin_id is automatically set to the current authenticated user's ID.
    This ensures admins can only assign agents to themselves, not to other admins.
    """
    # Use current_user.id as admin_id (from JWT token)
    admin_id = current_user.id
    
    # Check if agent exists
    stmt_agent = select(User).where(User.id == assign_in.agent_id)
    agent = db.execute(stmt_agent).scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    
    # Prevent self-assignment (admin assigning themselves as an agent)
    if admin_id == assign_in.agent_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="An admin cannot assign themselves as an agent"
        )
    
    # Get user's roles (users can have multiple roles via many-to-many relationship)
    role_names = {role.name for role in agent.roles}
    
    # Prevent assigning admins as agents
    if UserRoles.ADMIN in role_names:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Admins cannot be assigned as agents"
        )
    
    # Ensure target user has AGENT role (required for assignment)
    if UserRoles.AGENT not in role_names:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Only users with AGENT role can be assigned to an admin"
        )
    
    # Check if assignment already exists (active or inactive)
    stmt_existing = select(AdminAgentAssignment).where(
        and_(
            AdminAgentAssignment.admin_id == admin_id,
            AdminAgentAssignment.agent_id == assign_in.agent_id
        )
    )
    existing = db.execute(stmt_existing).scalar_one_or_none()
    
    if existing:
        # Reactivate existing assignment if it was previously revoked
        if not existing.is_active:
            existing.is_active = True
            existing.revoked_at = None
        # Update can_inherit_privileges in case it changed
        existing.can_inherit_privileges = assign_in.can_inherit_privileges
    else:
        # Create new assignment
        db_assignment = AdminAgentAssignment(
            admin_id=admin_id,
            agent_id=assign_in.agent_id,
            is_active=True,
            can_inherit_privileges=assign_in.can_inherit_privileges
        )
        db.add(db_assignment)
    
    try:
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_ASSIGNED, agent_id=str(assign_in.agent_id), admin_id=str(admin_id)))
        return create_success_response(data=True, message=SuccessMessages.AGENT_ASSIGNED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.ASSIGNMENT_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.ASSIGNMENT_FAILED)

@router.post("/unassign-agent", response_model=StandardResponse[bool])
def unassign_agent(unassign_in: AdminAgentAssignmentRequest, current_user: User = require_role(UserRoles.ADMIN), db: Session = Depends(get_db)):
    """
    Revoke an agent's inherited admin privileges.
    
    The admin_id is automatically set to the current authenticated user's ID.
    This ensures admins can only revoke assignments they created, not other admins' assignments.
    """
    # Use current_user.id as admin_id (from JWT token)
    admin_id = current_user.id
    
    # Find the assignment created by this admin
    stmt = select(AdminAgentAssignment).where(
        and_(
            AdminAgentAssignment.admin_id == admin_id,
            AdminAgentAssignment.agent_id == unassign_in.agent_id,
            AdminAgentAssignment.is_active == True
        )
    )
    assignment = db.execute(stmt).scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.ASSIGNMENT_NOT_FOUND)
        
    assignment.is_active = False
    assignment.revoked_at = datetime.now()
    
    try:
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_REVOKED, agent_id=str(unassign_in.agent_id), admin_id=str(admin_id)))
        return create_success_response(data=True, message=SuccessMessages.AGENT_REVOKED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.REVOCATION_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REVOCATION_FAILED)
