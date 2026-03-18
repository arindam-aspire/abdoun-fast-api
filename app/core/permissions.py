"""
Role-based and permission-based authorization decorators for FastAPI.

This module provides:
- require_role(role_name): Decorator factory that enforces a specific role
- require_permission(permission_code): Decorator factory that enforces a specific permission
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db.session import get_db
from app.core.auth import get_current_user
from app.models.user import User, Role, AdminAgentAssignment
from app.utils.constants import Defaults, ErrorMessages, UserRoles
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger


def get_user_permissions(user: User, db: Session) -> set[str]:
    """
    Collect all permissions for a user (from roles + inherited from admin assignments).
    
    Args:
        user: User model instance
        db: Database session
        
    Returns:
        set[str]: Set of permission codes the user has
    """
    permissions = set()
    
    # Direct role permissions
    for role in user.roles:
        for perm in role.permissions:
            permissions.add(perm.code)
    
    # If this user is an agent and has an active assignment from an admin,
    # they inherit the admin's permissions if can_inherit_privileges is True
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


def get_user_roles(user: User, db: Session) -> set[str]:
    """
    Collect all roles for a user (direct roles + inherited from admin assignments).
    
    Args:
        user: User model instance
        db: Database session
        
    Returns:
        set[str]: Set of role names the user has (directly or inherited)
    """
    role_names = {role.name for role in user.roles}
    
    # If this user is an agent and has an active assignment from an admin,
    # they inherit the admin's roles if can_inherit_privileges is True
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
            role_names.add(role.name)
    
    return role_names


class RoleChecker:
    """FastAPI dependency that enforces a required role for the current user."""

    def __init__(self, required_role: str):
        """Store the role name to enforce.

        Args:
            required_role: Role name (e.g. "admin", "agent") the user must have.
        """
        self.required_role = required_role
    
    def __call__(self, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        """
        Check if the current user has the required role (directly or inherited).
        
        Returns:
            User: The current user if they have the required role
            
        Raises:
            HTTPException 403: If user doesn't have the required role
        """
        # Get user roles (including inherited roles from admin assignments)
        user_role_names = get_user_roles(user, db)
        
        if self.required_role not in user_role_names:
            api_logger.warning(
                format_log_message(
                    LogMessages.RBAC.PERMISSION_DENIED,
                    user_id=str(user.id),
                    permission=f"{Defaults.ROLE_PERMISSION_PREFIX}{self.required_role}",
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=format_log_message(ErrorMessages.MISSING_ROLE, role=self.required_role),
            )
        
        return user


class PermissionChecker:
    """FastAPI dependency that enforces a required permission for the current user."""

    def __init__(self, required_permission: str):
        """Store the permission code to enforce.

        Args:
            required_permission: Permission code (e.g. "agent:approve") the user must have.
        """
        self.required_permission = required_permission
    
    def __call__(self, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        """
        Check if the current user has the required permission.
        
        Returns:
            User: The current user if they have the required permission
            
        Raises:
            HTTPException 403: If user doesn't have the required permission
        """
        user_perms = get_user_permissions(user, db)
        
        if self.required_permission not in user_perms:
            api_logger.warning(format_log_message(LogMessages.RBAC.PERMISSION_DENIED, user_id=str(user.id), permission=self.required_permission))
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=format_log_message(ErrorMessages.MISSING_PERMISSION, permission=self.required_permission),
            )
        
        return user


def require_role(role_name: str):
    """
    Decorator factory that returns a FastAPI dependency for role enforcement.
    
    Usage:
        @router.get("/admin-only")
        def admin_endpoint(current_user: User = require_role("admin")):
            ...
    
    Note: This function already returns Depends(...), so do NOT wrap it in Depends() again.
    
    Args:
        role_name: Name of the required role (e.g., "admin", "agent")
        
    Returns:
        FastAPI dependency that enforces the role
    """
    return Depends(RoleChecker(role_name))


def require_permission(permission_code: str):
    """
    Decorator factory that returns a FastAPI dependency for permission enforcement.
    
    Usage:
        @router.post("/invite")
        def invite_agent(current_user: User = require_permission("agent:invite")):
            ...
    
    Note: This function already returns Depends(...), so do NOT wrap it in Depends() again.
    
    Args:
        permission_code: Code of the required permission (e.g., "agent:invite")
        
    Returns:
        FastAPI dependency that enforces the permission
    """
    return Depends(PermissionChecker(permission_code))

