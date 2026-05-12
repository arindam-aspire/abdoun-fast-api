"""Service layer for admin property operations (assignment to agents)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.constants.notification_types import NotificationType
from app.repositories.property_admin_repository import PropertyAdminRepository
from app.services.notification_event_emitter import NotificationEmitPayload, NotificationEventEmitter
from app.services.translation_service import get_title_description_for_language
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.logger import api_logger
from app.utils.log_messages import format_log_message
from app.utils.status_codes import HTTPStatus


class PropertyAdminService:
    """Business logic for admin-only property mutations."""

    def __init__(
        self,
        repo: PropertyAdminRepository,
        *,
        notification_emitter: NotificationEventEmitter | None = None,
    ) -> None:
        self._repo = repo
        self._notification_emitter = notification_emitter

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

        previous_agent_id = prop.agent_user_id

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

        admin_actor = self._repo.get_user_with_roles(admin_user_id)
        admin_raw = getattr(admin_actor, "full_name", None) if admin_actor else None
        admin_display = str(admin_raw).strip() if admin_raw else "Unknown"

        try:
            prop.agent_user_id = resolved_agent_id
            prop.updated_by_user_id = admin_user_id
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

        if self._notification_emitter is not None and previous_agent_id != resolved_agent_id:
            title, _desc = get_title_description_for_language(prop, None)
            property_name = (title or "").strip() or "Property"
            property_id_str = str(prop.id)
            agent_roles = frozenset({UserRoles.AGENT})
            payloads: list[NotificationEmitPayload] = []

            if resolved_agent_id is not None:
                tk = NotificationType.PROPERTY_AGENT_ASSIGNED.value
                payloads.append(
                    NotificationEmitPayload(
                        event_type=tk,
                        type_key=tk,
                        recipient_user_id=resolved_agent_id,
                        actor_user_id=admin_user_id,
                        recipient_role_names=agent_roles,
                        template_data={
                            "property_name": property_name,
                            "property_id": property_id_str,
                            "admin_name": admin_display,
                            "entity_type": "property",
                            "entity_id": property_id_str,
                            "metadata": {"property_id": property_id_str},
                        },
                        idempotency_key=f"property.agent_assigned:{property_id_str}:{resolved_agent_id}",
                    )
                )
            if previous_agent_id is not None and previous_agent_id != resolved_agent_id:
                tk = NotificationType.PROPERTY_AGENT_UNASSIGNED.value
                payloads.append(
                    NotificationEmitPayload(
                        event_type=tk,
                        type_key=tk,
                        recipient_user_id=previous_agent_id,
                        actor_user_id=admin_user_id,
                        recipient_role_names=agent_roles,
                        template_data={
                            "property_name": property_name,
                            "property_id": property_id_str,
                            "admin_name": admin_display,
                            "entity_type": "property",
                            "entity_id": property_id_str,
                            "metadata": {"property_id": property_id_str},
                        },
                        idempotency_key=f"property.agent_unassigned:{property_id_str}:{previous_agent_id}:{resolved_agent_id or 'none'}",
                    )
                )
            if payloads:
                try:
                    self._notification_emitter.emit_bulk(payloads=payloads)
                except Exception:
                    api_logger.error(
                        format_log_message(
                            "Property assignment notification dispatch failed property_id={pid}",
                            pid=property_id_str,
                        ),
                        exc_info=True,
                    )

        return prop.id, prop.agent_user_id
