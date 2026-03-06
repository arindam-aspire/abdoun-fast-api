import secrets
import uuid
import math
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, and_, or_, func

from app.db.session import get_db
from app.core.config import get_settings
from app.models.user import User, Role, AgentInvite, AgentProfile, AdminAgentAssignment
from app.schemas.user import (
    AgentInviteRequest, AdminAgentAssignmentRequest,
    AgentOnboardingFormRequest, AgentOnboardingFormResponse, AgentValidateInviteResponse,
    AgentListResponse, AgentDetailResponse, AgentInviteResponse, AgentAcceptRequest,
    AgentAcceptResponse, AgentDeclineResponse, AgentDeleteResponse,
    AgentListPaginatedResponse, PaginationInfo
)
from app.utils.responses import StandardResponse, create_success_response
from app.utils.constants import SuccessMessages, ErrorMessages, InfoMessages, UserRoles, UserPermissions, AgentStatus, DevAuthDefaults
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger
from app.services.notification import notify_agent_approved, notify_agent_rejected, notify_agent_invite_sent
from app.services.cognito import cognito_service

router = APIRouter()
DEV_AGENT_USER_ID = uuid.UUID(DevAuthDefaults.USER_ID)


def get_dev_user(db: Session = Depends(get_db)) -> User:
    """Temporary auth bypass for agents routes during local development."""
    dev_user = db.get(User, DEV_AGENT_USER_ID)
    if dev_user:
        return dev_user

    dev_user = User(
        id=DEV_AGENT_USER_ID,
        full_name=DevAuthDefaults.FULL_NAME,
        email=DevAuthDefaults.EMAIL,
        phone_number=DevAuthDefaults.PHONE_NUMBER,
        is_active=True,
        is_email_verified=True,
        is_phone_verified=True,
    )
    db.add(dev_user)
    try:
        db.commit()
        db.refresh(dev_user)
        return dev_user
    except Exception:
        db.rollback()
        existing = db.get(User, DEV_AGENT_USER_ID)
        if existing:
            return existing
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ErrorMessages.DEV_AUTH_INIT_FAILED,
        )


# ============================================================================
# Admin Endpoints
# ============================================================================

@router.post("/invite", response_model=StandardResponse[AgentInviteResponse])
def invite_agent(
    invite_in: AgentInviteRequest,
    current_user: User = Depends(get_dev_user),
    db: Session = Depends(get_db)
):
    """
    Admin: Invite an agent.
    Creates an AgentInvite record and sends an invite email.
    """
    # Validate email format (Pydantic does this, but check for existing agent)
    stmt_user = select(User).where(User.email == invite_in.email)
    existing_user = db.execute(stmt_user).scalar_one_or_none()
    
    if existing_user:
        # Check if user already has an agent profile
        if existing_user.profile:
            api_logger.warning(format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=invite_in.email))
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.AGENT_ALREADY_EXISTS
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
        
        # Create User + AgentProfile with INVITED status if user doesn't exist
        db_user = existing_user
        if not existing_user:
            # `users.phone_number` is unique/non-null; use a temporary unique placeholder
            # until onboarding form submission provides the real number.
            placeholder_phone = f"+1999{uuid.uuid4().int % 10**8:08d}"
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
        else:
            # User exists but might not have profile - create it if missing
            if not existing_user.profile:
                db_profile = AgentProfile(
                    user_id=existing_user.id,
                    status=AgentStatus.INVITED
                )
                db.add(db_profile)
                db.commit()
                db.refresh(db_profile)
        
        return create_success_response(
            data=AgentInviteResponse(
                id=db_user.id,  # Use user ID, not invite ID
                email=db_invite.email,
                status=AgentStatus.INVITED,
                inviteLink=invite_link,
                invitedAt=db_invite.invited_at or db_invite.created_at,
                invitedBy=db_invite.invited_by
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
    current_user: User = Depends(get_dev_user),
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
    
    # Filter by status
    if status:
        stmt = stmt.where(AgentProfile.status == status)
    
    # Search by name or email
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )
    
    # Get total count before pagination
    # Create a count query
    count_query = (
        select(func.count(User.id))
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(AgentProfile.deleted_at.is_(None))
    )
    if status:
        count_query = count_query.where(AgentProfile.status == status)
    if search:
        search_pattern = f"%{search}%"
        count_query = count_query.where(
            or_(
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )
    total_items = db.execute(count_query).scalar() or 0
    
    # Apply sorting
    if sortBy == "invitedAt":
        order_col = AgentProfile.form_submitted_at if hasattr(AgentProfile, 'form_submitted_at') else User.created_at
    elif sortBy == "email":
        order_col = User.email
    elif sortBy == "fullName":
        order_col = User.full_name
    else:
        order_col = User.created_at
    
    if sortOrder.lower() == "asc":
        stmt = stmt.order_by(order_col.asc())
    else:
        stmt = stmt.order_by(order_col.desc())
    
    # Apply pagination
    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)
    
    results = db.execute(stmt).all()
    
    agents = []
    for user, profile in results:
        # Get invite info
        stmt_invite = select(AgentInvite).where(AgentInvite.email == user.email).order_by(AgentInvite.created_at.desc())
        invite_result = db.execute(stmt_invite).first()
        invite = invite_result[0] if invite_result else None
        
        agents.append(AgentListResponse(
            id=user.id,
            email=user.email,
            fullName=user.full_name if user.full_name else None,
            phone=user.phone_number if user.phone_number else None,
            serviceArea=profile.service_area,
            status=profile.status,
            invitedAt=invite.created_at if invite else None,
            invitedBy=invite.invited_by if invite else None,
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
    current_user: User = Depends(get_dev_user),
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


@router.get("/{agent_id}", response_model=StandardResponse[AgentDetailResponse])
def get_agent_details(
    agent_id: uuid.UUID = Path(..., description="Agent ID"),
    current_user: User = Depends(get_dev_user),
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
    stmt_invite = select(AgentInvite).where(AgentInvite.email == user.email).order_by(AgentInvite.created_at.desc())
    invite_result = db.execute(stmt_invite).first()
    invite = invite_result[0] if invite_result else None
    
    return create_success_response(
        data=AgentDetailResponse(
            id=user.id,
            email=user.email,
            fullName=user.full_name if user.full_name else None,
            phone=user.phone_number if user.phone_number else None,
            serviceArea=profile.service_area,
            status=profile.status,
            invitedAt=invite.created_at if invite else None,
            invitedBy=invite.invited_by if invite else None,
            formSubmittedAt=profile.form_submitted_at,
            reviewedAt=profile.reviewed_at,
            reviewedBy=profile.reviewed_by,
            declineReason=profile.decline_reason,
            passwordSetAt=profile.password_set_at
        )
    )


@router.patch("/{agent_id}/accept", response_model=StandardResponse[AgentAcceptResponse])
def accept_agent(
    agent_id: uuid.UUID = Path(..., description="Agent ID"),
    current_user: User = Depends(get_dev_user),
    db: Session = Depends(get_db)
):
    """
    Admin: Accept an agent (change status from PENDING_REVIEW to ACTIVE).
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
    
    if profile.status != AgentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_STATUS_TRANSITION
        )
    
    try:
        settings = get_settings()
        cognito_enabled = bool(settings.cognito_user_pool_id and settings.cognito_client_id)

        # Create user in Cognito if configured and not already created
        if not user.cognito_sub:
            if cognito_enabled:
                cognito_service.admin_create_user(
                    email=user.email,
                    full_name=user.full_name,
                    phone_number=user.phone_number
                )
            else:
                api_logger.warning(
                    format_log_message(
                        LogMessages.RBAC.NOTIFICATION_FAILED,
                        context="cognito create user skipped (missing config)",
                        error=f"user_id={user.id}",
                    )
                )
        
        # Update status to ACTIVE
        profile.status = AgentStatus.ACTIVE
        profile.reviewed_at = datetime.now()
        profile.reviewed_by = current_user.id
        profile.approved_by = current_user.id
        profile.approved_at = datetime.now()
        user.is_active = True
        
        db.commit()
        
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_APPROVED, agent_id=str(agent_id), approver_id=current_user.email))
        
        try:
            notify_agent_approved(user.email, user.full_name)
        except Exception as n:
            api_logger.warning(format_log_message(LogMessages.RBAC.NOTIFICATION_FAILED, context="agent approved", error=str(n)))
        
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
    agent_id: uuid.UUID = Path(..., description="Agent ID"),
    payload: Optional[dict] = Body(None),
    current_user: User = Depends(get_dev_user),
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


@router.delete("/{agent_id}", response_model=StandardResponse[AgentDeleteResponse])
def delete_agent(
    agent_id: uuid.UUID = Path(..., description="Agent ID"),
    current_user: User = Depends(get_dev_user),
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
        profile.status = "DELETED"  # Set status to DELETED
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
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=e.errors()) from e
    return _submit_onboarding_form(resolved_token, form_data, db)


# ============================================================================
# Legacy Endpoints (for backward compatibility)
# ============================================================================

# ============================================================================
# Admin-Agent Assignment Endpoints
# ============================================================================

@router.post("/assign-agent", response_model=StandardResponse[bool])
def assign_agent(assign_in: AdminAgentAssignmentRequest, current_user: User = Depends(get_dev_user), db: Session = Depends(get_db)):
    """Assign an agent to an admin for permission inheritance. Requires agent:assign permission."""
    # Check if admin and agent exist
    stmt_admin = select(User).where(User.id == assign_in.admin_id)
    admin = db.execute(stmt_admin).scalar_one_or_none()
    
    stmt_agent = select(User).where(User.id == assign_in.agent_id)
    agent = db.execute(stmt_agent).scalar_one_or_none()
    
    if not admin or not agent:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
        
    db_assignment = AdminAgentAssignment(
        admin_id=assign_in.admin_id,
        agent_id=assign_in.agent_id,
        is_active=True,
        can_inherit_privileges=assign_in.can_inherit_privileges
    )
    db.add(db_assignment)
    
    try:
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_ASSIGNED, agent_id=str(assign_in.agent_id), admin_id=str(assign_in.admin_id)))
        return create_success_response(data=True, message=SuccessMessages.AGENT_ASSIGNED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.ASSIGNMENT_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.ASSIGNMENT_FAILED)

@router.post("/unassign-agent", response_model=StandardResponse[bool])
def unassign_agent(unassign_in: AdminAgentAssignmentRequest, current_user: User = Depends(get_dev_user), db: Session = Depends(get_db)):
    """Revoke an agent's inherited admin privileges."""
    stmt = select(AdminAgentAssignment).where(
        and_(
            AdminAgentAssignment.admin_id == unassign_in.admin_id,
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
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_REVOKED, agent_id=str(unassign_in.agent_id), admin_id=str(unassign_in.admin_id)))
        return create_success_response(data=True, message=SuccessMessages.AGENT_REVOKED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.REVOCATION_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REVOCATION_FAILED)

