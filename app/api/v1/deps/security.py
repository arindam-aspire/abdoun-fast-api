from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db.session import get_db
from app.services.cognito import cognito_service
from app.models.user import User, AdminAgentAssignment
from app.utils.constants import ErrorMessages, UserRoles, UserPermissions
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger

security = HTTPBearer()

async def get_current_user(
    res: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Resolve current user from Bearer token. Verifies Cognito JWT and loads User from DB."""
    token = res.credentials
    payload = cognito_service.verify_token(token)
    
    if not payload:
        api_logger.warning(LogMessages.Auth.TOKEN_VERIFICATION_FAILED_DEP)
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=ErrorMessages.INVALID_TOKEN,
        )
    
    cognito_sub = payload.get("sub")
    if not cognito_sub:
        api_logger.warning(LogMessages.Auth.TOKEN_PAYLOAD_MISSING_SUB)
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=ErrorMessages.MISSING_SUB,
        )
    
    # Get user from DB
    stmt = select(User).where(User.cognito_sub == cognito_sub)
    result = db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        # Fallback: token may be access token (no email claim) — get email from Cognito by sub and sync
        email = payload.get("email")
        if not email:
            attrs = cognito_service.get_user_attributes_by_sub(cognito_sub)
            if attrs:
                email = attrs.get("email")
        if email:
            stmt = select(User).where(User.email == email)
            result = db.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                # Sync cognito_sub so next time we find by sub
                user.cognito_sub = cognito_sub
                db.commit()
                db.refresh(user)
    
    # Sync email/phone verified from Cognito token (Cognito sets these after confirm or social login)
    if user:
        updated = False
        if payload.get("email_verified") is True and not user.is_email_verified:
            user.is_email_verified = True
            updated = True
        if payload.get("phone_number_verified") is True and not user.is_phone_verified:
            user.is_phone_verified = True
            updated = True
        if updated:
            db.commit()
            db.refresh(user)
    
    if not user:
        api_logger.warning(format_log_message(LogMessages.Auth.USER_NOT_FOUND_SUB, sub=cognito_sub))
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=ErrorMessages.USER_NOT_FOUND,
        )
    
    if not user.is_active:
        api_logger.warning(format_log_message(LogMessages.Auth.INACTIVE_USER_ATTEMPT, email=user.email))
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=ErrorMessages.USER_INACTIVE,
        )
        
    return user


def get_user_permissions(user: User, db: Session) -> set[str]:
    """Collect all permissions for a user (roles + inherited from admin assignments)."""
    permissions = set()
    
    # Direct role permissions
    for role in user.roles:
        for perm in role.permissions:
            permissions.add(perm.code)
            
    # If this user is an agent and has an active assignment from an admin, 
    # they inherit the admin's permissions if can_inherit_privileges is True.
    stmt = select(AdminAgentAssignment).where(
        and_(
            AdminAgentAssignment.agent_id == user.id,
            AdminAgentAssignment.is_active == True,
            AdminAgentAssignment.can_inherit_privileges == True
        )
    )
    result = db.execute(stmt)
    assignments = result.scalars().all()
    
    for assignment in assignments:
        api_logger.debug(format_log_message(LogMessages.RBAC.INHERITANCE_TRIGGERED, user_id=str(user.id), admin_id=str(assignment.admin_id)))
        admin_user = assignment.admin
        for role in admin_user.roles:
            for perm in role.permissions:
                permissions.add(perm.code)
                
    return permissions


class PermissionChecker:
    """FastAPI dependency that enforces a required permission for the current user."""

    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        user_perms = get_user_permissions(user, db)
        
        if self.required_permission not in user_perms:
            api_logger.warning(format_log_message(LogMessages.RBAC.PERMISSION_DENIED, user_id=str(user.id), permission=self.required_permission))
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=format_log_message(ErrorMessages.MISSING_PERMISSION, permission=self.required_permission),
            )
        return True

def require_permission(permission_code: str):
    """Return FastAPI dependency for route-level permission enforcement."""
    return Depends(PermissionChecker(permission_code))
