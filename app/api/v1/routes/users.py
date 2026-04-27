"""
User, role, and permission management endpoints.
Admin-only: list users, get/update/delete user, assign/remove roles, list roles and permissions.
"""

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.media_urls import get_media_url_signer
from app.api.v1.deps.security import get_current_user, require_permission
from app.api.v1.deps.users import get_user_service
from app.models.user import User
from app.schemas.user import (
    RoleAssignmentRequest,
    RoleResponse,
    UserResponse,
    UserTypeQuery,
    UserUpdate,
    UsersListPaginatedResponse,
)
from app.services.media_url_signer import MediaUrlSigner
from app.services.user_service import UserService
from app.utils.constants import ApiDocs, SuccessMessages, UserPermissions
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get(
    "",
    response_model=StandardResponse[UsersListPaginatedResponse],
    dependencies=[require_permission(UserPermissions.USER_CREATE)],
)
def list_users(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
    page: Annotated[int, Query(ge=1, description=ApiDocs.PAGE_NUMBER_1_BASED)] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=200, alias="pageSize", description=ApiDocs.ITEMS_PER_PAGE)
    ] = 50,
    user_type: Annotated[
        Optional[UserTypeQuery], Query(alias="userType", description=ApiDocs.USER_TYPE_FILTER)
    ] = None,
    role_name: Annotated[Optional[str], Query(description=ApiDocs.FILTER_BY_ROLE)] = None,
    search: Annotated[Optional[str], Query(description=ApiDocs.SEARCH_USERS)] = None,
    is_active: Annotated[
        Optional[bool], Query(description=ApiDocs.FILTER_USERS_BY_IS_ACTIVE)
    ] = None,
):
    """List users with page-based pagination (like property search) and optional ``userType`` role filter.

    If ``userType`` is set, it takes precedence over ``role_name``. ``register_user`` maps to the
    ``registered_user`` role in the database. If both are omitted, all users matching ``search`` are listed.
    Pass ``is_active=true`` or ``is_active=false`` to restrict to active or inactive users only.
    Soft-deleted users are never included.
    """
    users, total = service.list_users(
        page=page,
        page_size=page_size,
        user_type=user_type,
        role_name=role_name,
        search=search,
        is_active=is_active,
    )
    body = UsersListPaginatedResponse(
        users=[media_signer.user_response_from_orm(u) for u in users],
        total=total,
        page=page,
        pageSize=page_size,
    )
    return create_success_response(data=body, message=None)


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
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
):
    """Get user by ID. Requires user:create permission."""
    user = service.get_user(id)
    return create_success_response(data=media_signer.user_response_from_orm(user), message=None)


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
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
):
    """Update user (full_name, phone_number, is_active). Requires user:create permission."""
    user = service.update_user(user_id=id, body=body, current_user=current_user)
    return create_success_response(
        data=media_signer.user_response_from_orm(user), message=SuccessMessages.USER_UPDATED
    )


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
    """Soft-delete user (sets ``deleted_at``, ``deleted_by``, and ``is_active`` to false). Restore is not supported."""
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
