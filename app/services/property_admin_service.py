"""Service layer for admin property operations (assignment to agents)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.repositories.property_admin_repository import PropertyAdminRepository
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.status_codes import HTTPStatus


class PropertyAdminService:
    """Business logic for admin-only property mutations."""

    def __init__(self, repo: PropertyAdminRepository) -> None:
        self._repo = repo

    def assign_agent_to_property(
        self,
        *,
        property_id: uuid.UUID,
        agent_id: uuid.UUID | None,
        admin_user_id: uuid.UUID,
    ) -> tuple[uuid.UUID, uuid.UUID | None]:
        prop = self._repo.get_property(property_id)
        if prop is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.PROPERTY_NOT_FOUND)

        resolved_agent_id: uuid.UUID | None = None
        if agent_id is not None:
            agent_user = self._repo.get_user_with_roles(agent_id)
            if agent_user is None:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.USER_NOT_FOUND)

            role_names = {r.name for r in (agent_user.roles or [])}
            if UserRoles.ADMIN in role_names:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.ADMINS_CANNOT_BE_ASSIGNED_AS_AGENTS,
                )
            if UserRoles.AGENT not in role_names:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.ONLY_AGENT_ROLE_CAN_BE_ASSIGNED_TO_ADMIN,
                )
            resolved_agent_id = agent_user.id

        try:
            prop.agent_user_id = resolved_agent_id
            prop.updated_by_user_id = admin_user_id
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

        return prop.id, prop.agent_user_id

