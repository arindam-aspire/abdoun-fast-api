"""User, role, and permission service: list/get/update/delete users, assign/remove roles; uses UserRepository."""
import uuid
from typing import List, Optional, Tuple

from fastapi import HTTPException

from app.repositories.user_repository import UserRepository
from app.schemas.user import RoleAssignmentRequest, UserTypeQuery, UserUpdate
from app.utils.constants import USER_TYPE_QUERY_TO_ROLE_NAME, ErrorMessages
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.status_codes import HTTPStatus
from app.models.user import Role, User


class UserService:
    """Service layer for user, role and permission operations."""

    def __init__(self, repository: UserRepository) -> None:
        """Store the user repository for all operations.

        Args:
            repository: UserRepository instance (request-scoped).
        """
        self._repo = repository

    # Queries

    def list_users(
        self,
        *,
        page: int,
        page_size: int,
        user_type: Optional[UserTypeQuery],
        role_name: Optional[str],
        search: Optional[str],
        is_active: Optional[bool] = None,
    ) -> Tuple[List[User], int]:
        """List users with optional ``userType`` / ``role_name``, ``is_active``, search, and pagination."""
        effective_role: Optional[str] = None
        if user_type is not None:
            effective_role = USER_TYPE_QUERY_TO_ROLE_NAME[user_type.value]
        elif role_name:
            effective_role = role_name

        offset = (page - 1) * page_size
        total = self._repo.count_users(
            role_name=effective_role,
            search=search,
            is_active=is_active,
        )
        users = self._repo.list_users(
            limit=page_size,
            offset=offset,
            role_name=effective_role,
            search=search,
            is_active=is_active,
        )
        return users, total

    def list_roles(self) -> List[Role]:
        """List all roles with permissions loaded."""
        return self._repo.list_roles_with_permissions()

    def list_permissions(self) -> List[dict]:
        """List all permissions as dicts with id, code, description."""
        perms = self._repo.list_permissions()
        return [
            {"id": str(p.id), "code": p.code, "description": p.description}
            for p in perms
        ]

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self._repo.get_user_with_roles_and_profile(user_id)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        return user

    # Mutations

    def update_user(self, *, user_id: uuid.UUID, body: UserUpdate, current_user: User) -> User:
        user = self._repo.get_user_with_roles_and_profile(user_id)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        try:
            if body.full_name is not None:
                user.full_name = body.full_name
            if body.phone_number is not None:
                user.phone_number = body.phone_number
            if body.is_active is not None:
                user.is_active = body.is_active
            self._repo.commit()
            self._repo.refresh(user)
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.USER_UPDATED_LOG,
                    user_id=str(user_id),
                    admin_email=current_user.email,
                )
            )
            return user
        except Exception as e:  # pragma: no cover - defensive, same as legacy
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.REGISTRATION_FAILED_LOG, error=str(e)
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REGISTRATION_FAILED,
            )

    def delete_user(self, *, user_id: uuid.UUID, current_user: User) -> bool:
        user = self._repo.get_user_by_id_including_deleted(user_id)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        if user.deleted_at is not None:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_ALREADY_SOFT_DELETED,
            )
        if user.id == current_user.id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.CANNOT_DEACTIVATE_SELF,
            )
        try:
            self._repo.soft_delete_user(user, deleted_by_id=current_user.id)
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.USER_DELETED_LOG,
                    user_id=str(user_id),
                    admin_email=current_user.email,
                )
            )
            return True
        except Exception as ex:  # pragma: no cover - defensive
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.USER_DELETE_FAILED_LOG, error=str(ex)
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REGISTRATION_FAILED,
            )

    def assign_role(
        self,
        *,
        user_id: uuid.UUID,
        body: RoleAssignmentRequest,
        current_user: User,
    ) -> bool:
        user = self._repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        role = self._repo.get_role_by_id(body.role_id)
        if not role:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.ROLE_NOT_FOUND,
            )
        if role in user.roles:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_ALREADY_HAS_ROLE,
            )
        try:
            self._repo.assign_role_to_user(
                user=user,
                role=role,
                assigned_by=current_user.id,
            )
            self._repo.commit()
            self._repo.refresh(user)
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.ROLE_ASSIGNED_LOG,
                    role_name=role.name,
                    user_id=str(user_id),
                    admin_email=current_user.email,
                )
            )
            return True
        except Exception as ex:  # pragma: no cover - defensive
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.ROLE_ASSIGN_FAILED_LOG, error=str(ex)
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.ASSIGNMENT_FAILED,
            )

    def remove_role(
        self,
        *,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        current_user: User,
    ) -> bool:
        user = self._repo.get_user_with_roles_and_profile(user_id)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        role: Optional[Role] = next((r for r in user.roles if r.id == role_id), None)
        if not role:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_DOES_NOT_HAVE_ROLE,
            )
        try:
            self._repo.remove_role_from_user(user=user, role=role)
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.ROLE_REMOVED_LOG,
                    role_name=role.name,
                    user_id=str(user_id),
                    admin_email=current_user.email,
                )
            )
            return True
        except Exception as ex:  # pragma: no cover - defensive
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.ROLE_REMOVED_FAILED_LOG, error=str(ex)
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REVOCATION_FAILED,
            )

