"""
User, role, and permission management endpoints.
Admin-only: list users, get/update/delete user, assign/remove roles, list roles and permissions.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps.security import get_current_user, require_permission
from app.api.v1.deps.users import get_user_service
from app.core.limiter import limiter
from app.models.user import User
from app.schemas.user import (
    RoleAssignmentRequest,
    RoleResponse,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import UserService
from app.utils.constants import SuccessMessages, UserPermissions
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get(
    "",
    response_model=StandardResponse[List[UserResponse]],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
@limiter.limit("60/minute")
def list_users(
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    role_name: Optional[str] = Query(
        None, description="Filter by role (admin, agent, registered_user)"
    ),
    search: Optional[str] = Query(
        None, description="Search by email, phone number, or full_name"
    ),
    service: UserService = Depends(get_user_service),
):
    """List users with pagination and optional filters. Requires user:create permission."""
    users = service.list_users(
        limit=limit,
        offset=offset,
        role_name=role_name,
        search=search,
    )
    return create_success_response(data=users, message=None)


@router.get(
    "/roles/list",
    response_model=StandardResponse[List[RoleResponse]],
    dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)],
)
@limiter.limit("60/minute")
def list_roles(
    request: Request,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """List all roles with their permissions. Requires role:assign permission."""
    roles = service.list_roles()
    return create_success_response(data=roles, message=None)


@router.get(
    "/permissions/list",
    response_model=StandardResponse[List[dict]],
    dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)],
)
@limiter.limit("60/minute")
def list_permissions(
    request: Request,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """List all permissions. Requires role:assign permission."""
    data = service.list_permissions()
    return create_success_response(data=data, message=None)


@router.get(
    "/{id}",
    response_model=StandardResponse[UserResponse],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
@limiter.limit("60/minute")
def get_user(
    request: Request,
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Get user by ID. Requires user:create permission."""
    user = service.get_user(id)
    return create_success_response(data=user, message=None)


@router.patch(
    "/{id}",
    response_model=StandardResponse[UserResponse],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
@limiter.limit("30/minute")
def update_user(
    request: Request,
    id: uuid.UUID,
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Update user (full_name, phone_number, is_active). Requires user:create permission."""
    user = service.update_user(user_id=id, body=body, current_user=current_user)
    return create_success_response(data=user, message=SuccessMessages.USER_UPDATED)


@router.delete(
    "/{id}",
    response_model=StandardResponse[bool],
    dependencies=[require_permission(UserPermissions.USER_DELETE)],
)
@limiter.limit("10/minute")
def delete_user(
    request: Request,
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Soft-delete user (set is_active=False). Requires user:delete permission."""
    success = service.delete_user(user_id=id, current_user=current_user)
    return create_success_response(data=success, message=SuccessMessages.USER_DELETED)


@router.post(
    "/{id}/roles",
    response_model=StandardResponse[bool],
    dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)],
)
@limiter.limit("30/minute")
def assign_role(
    request: Request,
    id: uuid.UUID,
    body: RoleAssignmentRequest,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Assign a role to a user. Sets assigned_by for audit. Requires role:assign permission."""
    success = service.assign_role(
        user_id=id,
        body=body,
        current_user=current_user,
    )
    return create_success_response(
        data=success, message=SuccessMessages.ROLE_ASSIGNED_TO_USER
    )


@router.delete(
    "/{id}/roles/{role_id}",
    response_model=StandardResponse[bool],
    dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)],
)
@limiter.limit("30/minute")
def remove_role(
    request: Request,
    id: uuid.UUID,
    role_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Remove a role from a user. Requires role:assign permission."""
    success = service.remove_role(
        user_id=id,
        role_id=role_id,
        current_user=current_user,
    )
    return create_success_response(
        data=success, message=SuccessMessages.ROLE_REMOVED_FROM_USER
    )
