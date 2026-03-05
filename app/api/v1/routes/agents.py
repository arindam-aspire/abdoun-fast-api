import secrets
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, and_

from app.db.session import get_db
from app.core.config import get_settings
from app.api.v1.deps.security import get_current_user, require_permission
from app.models.user import User, Role, AgentInvite, AgentProfile, AdminAgentAssignment
from app.schemas.user import AgentInviteRequest, AgentRegister, UserResponse, AdminAgentAssignmentRequest
from app.utils.responses import StandardResponse, create_success_response
from app.utils.constants import SuccessMessages, ErrorMessages, UserRoles, UserPermissions, AgentStatus
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger
from app.services.notification import notify_agent_approved, notify_agent_rejected, notify_agent_invite_sent

router = APIRouter()

@router.post("/invite", response_model=StandardResponse[dict], dependencies=[require_permission(UserPermissions.AGENT_APPROVE)])
def invite_agent(invite_in: AgentInviteRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create an agent invitation. Requires agent:approve permission."""
    # Check if already invited or user exists
    stmt = select(User).where(User.email == invite_in.email)
    if db.execute(stmt).first():
        api_logger.warning(format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=invite_in.email))
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.USER_EXISTS)
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)
    
    db_invite = AgentInvite(
        email=invite_in.email,
        invited_by=current_user.id,
        token=token,
        expires_at=expires_at
    )
    db.add(db_invite)
    
    try:
        db.commit()
        settings = get_settings()
        invite_link = f"{settings.app_base_url.rstrip('/')}/agent-invite?token={token}"
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_INVITED, email=invite_in.email, invited_by=current_user.email))
        try:
            notify_agent_invite_sent(invite_in.email, invite_link, current_user.email)
        except Exception as n:
            api_logger.warning(format_log_message(LogMessages.RBAC.NOTIFICATION_FAILED, context="agent invite", error=str(n)))
        return create_success_response(
            data={"token": token, "expires_at": expires_at, "invite_link": invite_link},
            message=SuccessMessages.AGENT_INVITED,
        )
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INVITE_FAILED)

@router.get("/invite/validate", response_model=StandardResponse[dict])
def validate_invite(token: str = Query(...), db: Session = Depends(get_db)):
    """Validate an invite token and return the associated email. No auth required."""
    stmt = select(AgentInvite).where(
        and_(
            AgentInvite.token == token,
            AgentInvite.is_used == False,
            AgentInvite.expires_at > datetime.now()
        )
    )
    invite = db.execute(stmt).scalar_one_or_none()
    
    if not invite:
        api_logger.warning(format_log_message(LogMessages.RBAC.INVALID_INVITE_TOKEN_USED, token=token))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.INVALID_INVITE_TOKEN)
    
    return create_success_response(data={"email": invite.email}, message=SuccessMessages.INVITE_VALID)

@router.post("/register", response_model=StandardResponse[UserResponse])
def register_agent(agent_in: AgentRegister, db: Session = Depends(get_db)):
    """Complete agent registration using invite token. User created inactive until admin approval."""
    # Validate token
    stmt_invite = select(AgentInvite).where(
        and_(
            AgentInvite.token == agent_in.token,
            AgentInvite.is_used == False,
            AgentInvite.expires_at > datetime.now()
        )
    )
    invite = db.execute(stmt_invite).scalar_one_or_none()
    
    if not invite:
        api_logger.warning(LogMessages.RBAC.INVALID_REGISTRATION_TOKEN)
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.INVITE_EXPIRED)

    # Email comes from the invite (token); form only has full_name, phone_number, service_area
    try:
        # Create User & Agent Profile in DB
        db_user = User(
            email=invite.email,
            full_name=agent_in.full_name,
            phone_number=agent_in.phone_number,
            is_active=False # Pending approval
        )
        db.add(db_user)
        db.flush() # Get user ID
        
        # Assign Agent role
        stmt_role = select(Role).where(Role.name == UserRoles.AGENT)
        role = db.execute(stmt_role).scalar_one_or_none()
        if role:
            db_user.roles.append(role)
            
        # Create Agent Profile
        db_profile = AgentProfile(
            user_id=db_user.id,
            service_area=agent_in.service_area,
            status=AgentStatus.PENDING
        )
        db.add(db_profile)
        
        # Mark invite as used
        invite.is_used = True
        
        db.commit()
        db.refresh(db_user)
        
        api_logger.info(format_log_message(LogMessages.RBAC.REGISTRATION_PENDING, email=db_user.email))
        return create_success_response(data=db_user, message=SuccessMessages.AGENT_REGISTERED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.REGISTRATION_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.REGISTRATION_FAILED)

@router.post("/{id}/approve", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.AGENT_APPROVE)])
def approve_agent(id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Approve a pending agent. Creates user in Cognito and sets status to approved."""
    stmt = select(User).where(User.id == id).options(selectinload(User.profile))
    user = db.execute(stmt).scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
        
    if not user.profile:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.NOT_AN_AGENT)
        
    try:
        cognito_service.admin_create_user(
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number
        )
        
        user.is_active = True
        user.profile.status = AgentStatus.APPROVED
        user.profile.approved_by = current_user.id
        user.profile.approved_at = datetime.now()
        
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_APPROVED, agent_id=str(id), approver_id=current_user.email))
        try:
            notify_agent_approved(user.email, user.full_name)
        except Exception as n:
            api_logger.warning(format_log_message(LogMessages.RBAC.NOTIFICATION_FAILED, context="agent approved", error=str(n)))
        return create_success_response(data=True, message=SuccessMessages.AGENT_APPROVED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.APPROVAL_FAILED_LOG, agent_id=str(id), error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.APPROVAL_FAILED)


@router.post("/{id}/reject", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.AGENT_APPROVE)])
def reject_agent(id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Reject a pending agent application."""
    stmt = select(User).where(User.id == id).options(selectinload(User.profile))
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    if not user.profile:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.NOT_AN_AGENT)
    if user.profile.status != AgentStatus.PENDING:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.AGENT_NOT_PENDING)
    try:
        user.profile.status = AgentStatus.REJECTED
        user.profile.approved_by = current_user.id
        user.profile.approved_at = datetime.now()
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.AGENT_REJECTED, agent_id=str(id), rejector_id=current_user.email))
        try:
            notify_agent_rejected(user.email, user.full_name)
        except Exception as n:
            api_logger.warning(format_log_message(LogMessages.RBAC.NOTIFICATION_FAILED, context="agent rejected", error=str(n)))
        return create_success_response(data=True, message=SuccessMessages.AGENT_REJECTED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.AGENT_REJECT_FAILED_LOG, agent_id=str(id), error=str(e)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.AGENT_REJECT_FAILED)


@router.get("/pending", response_model=StandardResponse[List[UserResponse]], dependencies=[require_permission(UserPermissions.AGENT_APPROVE)])
def list_pending_agents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List agents with status pending (for admin approval)."""
    stmt = (
        select(User)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .where(AgentProfile.status == AgentStatus.PENDING)
        .options(selectinload(User.roles))
    )
    users = list(db.execute(stmt).scalars().unique().all())
    return create_success_response(data=users, message=None)


@router.get("/invites", response_model=StandardResponse[List[dict]], dependencies=[require_permission(UserPermissions.AGENT_APPROVE)])
def list_invites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    used: Optional[bool] = Query(None, description="Filter by is_used: true/false"),
):
    """List agent invites (optionally filter by used)."""
    stmt = select(AgentInvite).where(AgentInvite.invited_by == current_user.id)
    if used is not None:
        stmt = stmt.where(AgentInvite.is_used == used)
    stmt = stmt.order_by(AgentInvite.created_at.desc())
    invites = db.execute(stmt).scalars().all()
    data = [
        {
            "id": str(inv.id),
            "email": inv.email,
            "expires_at": inv.expires_at,
            "is_used": inv.is_used,
            "created_at": inv.created_at,
        }
        for inv in invites
    ]
    return create_success_response(data=data, message=None)

@router.post("/assign-agent", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.AGENT_ASSIGN)])
def assign_agent(assign_in: AdminAgentAssignmentRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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

@router.post("/unassign-agent", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.AGENT_ASSIGN)])
def unassign_agent(unassign_in: AdminAgentAssignmentRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
