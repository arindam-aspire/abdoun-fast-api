"""
User, role, and permission management endpoints.
Admin-only: list users, get/update/delete user, assign/remove roles, list roles and permissions.
"""

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.security import get_current_user, require_permission
from app.api.v1.deps.users import get_user_service
from app.models.user import User
from app.schemas.user import (
    RoleAssignmentRequest,
    RoleResponse,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import UserService
from app.utils.constants import ApiDocs, SuccessMessages, UserPermissions
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get(
    "",
    response_model=StandardResponse[List[UserResponse]],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
def list_users(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    role_name: Annotated[Optional[str], Query(description=ApiDocs.FILTER_BY_ROLE)] = None,
    search: Annotated[Optional[str], Query(description=ApiDocs.SEARCH_USERS)] = None,
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
def list_roles(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """List all roles with their permissions. Requires role:assign permission."""
    roles = service.list_roles()
    return create_success_response(data=roles, message=None)


@router.get(
    "/permissions/list",
    response_model=StandardResponse[List[dict]],
    dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)],
)
def list_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """List all permissions. Requires role:assign permission."""
    data = service.list_permissions()
    return create_success_response(data=data, message=None)


@router.get(
    "/{id}",
    response_model=StandardResponse[UserResponse],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
def get_user(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """Get user by ID. Requires user:create permission."""
    user = service.get_user(id)
    return create_success_response(data=user, message=None)


@router.patch(
    "/{id}",
    response_model=StandardResponse[UserResponse],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
def update_user(
    id: uuid.UUID,
    body: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """Update user (full_name, phone_number, is_active). Requires user:create permission."""
    user = service.update_user(user_id=id, body=body, current_user=current_user)
    return create_success_response(data=user, message=SuccessMessages.USER_UPDATED)


@router.delete(
    "/{id}",
    response_model=StandardResponse[bool],
    dependencies=[require_permission(UserPermissions.USER_DELETE)],
)
def delete_user(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
):
    """Soft-delete user (set is_active=False). Requires user:delete permission."""
    success = service.delete_user(user_id=id, current_user=current_user)
    return create_success_response(data=success, message=SuccessMessages.USER_DELETED)


@router.post(
    "/{id}/roles",
    response_model=StandardResponse[bool],
    dependencies=[require_permission(UserPermissions.ROLE_ASSIGN)],
)
def assign_role(
    id: uuid.UUID,
    body: RoleAssignmentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
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
def remove_role(
    id: uuid.UUID,
    role_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
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
