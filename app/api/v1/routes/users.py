"""
User, role, and permission management endpoints.
Admin-only: list users, get/update/delete user, assign/remove roles, list roles and permissions.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, insert
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.api.v1.deps.security import get_current_user, require_permission
from app.models.user import User, Role, Permission, user_roles
from app.schemas.user import UserResponse, UserUpdate, RoleAssignmentRequest, RoleResponse
from app.utils.responses import StandardResponse, create_success_response
from app.utils.constants import SuccessMessages, ErrorMessages, UserPermissions
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger

router = APIRouter()


@router.get("", response_model=StandardResponse[List[UserResponse]], dependencies=[require_permission(UserPermissions.USER_CREATE)])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    role_name: Optional[str] = Query(None, description="Filter by role (admin, agent, registered_user)"),
    search: Optional[str] = Query(None, description="Search by email, phone number, or full_name"),
):
    """List users with pagination and optional filters. Requires user:create permission."""
    stmt = select(User).options(selectinload(User.roles))
    if role_name:
        stmt = stmt.join(User.roles).where(Role.name == role_name)
    if search and search.strip():
        q = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(q), User.full_name.ilike(q), User.phone_number.ilike(q)))
    stmt = stmt.offset(offset).limit(limit).distinct()
    users = list(db.execute(stmt).scalars().unique().all())
    return create_success_response(data=users, message=None)


@router.get("/roles/list", response_model=StandardResponse[List[RoleResponse]], dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)])
def list_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all roles with their permissions. Requires role:assign permission."""
    stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    roles = list(db.execute(stmt).scalars().unique().all())
    return create_success_response(data=roles, message=None)


@router.get("/permissions/list", response_model=StandardResponse[List[dict]], dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)])
def list_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all permissions. Requires role:assign permission."""
    stmt = select(Permission).order_by(Permission.code)
    perms = list(db.execute(stmt).scalars().all())
    data = [{"id": str(p.id), "code": p.code, "description": p.description} for p in perms]
    return create_success_response(data=data, message=None)


@router.get("/{id}", response_model=StandardResponse[UserResponse], dependencies=[require_permission(UserPermissions.USER_CREATE)])
def get_user(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user by ID. Requires user:create permission."""
    stmt = select(User).where(User.id == id).options(selectinload(User.roles), selectinload(User.profile))
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    return create_success_response(data=user, message=None)


@router.patch("/{id}", response_model=StandardResponse[UserResponse], dependencies=[require_permission(UserPermissions.USER_CREATE)])
def update_user(
    id: uuid.UUID,
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user (full_name, phone_number, is_active). Requires user:create permission."""
    stmt = select(User).where(User.id == id).options(selectinload(User.roles))
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    try:
        if body.full_name is not None:
            user.full_name = body.full_name
        if body.phone_number is not None:
            user.phone_number = body.phone_number
        if body.is_active is not None:
            user.is_active = body.is_active
        db.commit()
        db.refresh(user)
        api_logger.info(format_log_message(LogMessages.RBAC.USER_UPDATED_LOG, user_id=str(id), admin_email=current_user.email))
        return create_success_response(data=user, message=SuccessMessages.USER_UPDATED)
    except Exception as e:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.REGISTRATION_FAILED_LOG, error=str(e)))
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.REGISTRATION_FAILED)


@router.delete("/{id}", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.USER_DELETE)])
def delete_user(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete user (set is_active=False). Requires user:delete permission."""
    stmt = select(User).where(User.id == id)
    user = db.execute(stmt).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    if user.id == current_user.id:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.CANNOT_DEACTIVATE_SELF)
    try:
        user.is_active = False
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.USER_DELETED_LOG, user_id=str(id), admin_email=current_user.email))
        return create_success_response(data=True, message=SuccessMessages.USER_DELETED)
    except Exception as ex:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.USER_DELETE_FAILED_LOG, error=str(ex)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REGISTRATION_FAILED)


@router.post("/{id}/roles", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)])
def assign_role(
    id: uuid.UUID,
    body: RoleAssignmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assign a role to a user. Sets assigned_by for audit. Requires role:assign permission."""
    stmt_user = select(User).where(User.id == id)
    user = db.execute(stmt_user).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    stmt_role = select(Role).where(Role.id == body.role_id)
    role = db.execute(stmt_role).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.ROLE_NOT_FOUND)
    if role in user.roles:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.USER_ALREADY_HAS_ROLE)
    try:
        db.execute(insert(user_roles).values(
            user_id=user.id,
            role_id=role.id,
            assigned_by=current_user.id,
        ))
        db.commit()
        db.refresh(user)
        api_logger.info(format_log_message(LogMessages.RBAC.ROLE_ASSIGNED_LOG, role_name=role.name, user_id=str(id), admin_email=current_user.email))
        return create_success_response(data=True, message=SuccessMessages.ROLE_ASSIGNED_TO_USER)
    except Exception as ex:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.ROLE_ASSIGN_FAILED_LOG, error=str(ex)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.ASSIGNMENT_FAILED)


@router.delete("/{id}/roles/{role_id}", response_model=StandardResponse[bool], dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)])
def remove_role(
    id: uuid.UUID,
    role_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a role from a user. Requires role:assign permission."""
    stmt_user = select(User).where(User.id == id).options(selectinload(User.roles))
    user = db.execute(stmt_user).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)
    role = next((r for r in user.roles if r.id == role_id), None)
    if not role:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_DOES_NOT_HAVE_ROLE)
    try:
        user.roles.remove(role)
        db.commit()
        api_logger.info(format_log_message(LogMessages.RBAC.ROLE_REMOVED_LOG, role_name=role.name, user_id=str(id), admin_email=current_user.email))
        return create_success_response(data=True, message=SuccessMessages.ROLE_REMOVED_FROM_USER)
    except Exception as ex:
        db.rollback()
        api_logger.error(format_log_message(LogMessages.RBAC.ROLE_REMOVED_FAILED_LOG, error=str(ex)))
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REVOCATION_FAILED)
