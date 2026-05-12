"""Central routing for in-app notification deep-links (action_url).

Domain services must not hardcode client paths; resolve them here from
(event_type, recipient roles, optional context).
"""

from __future__ import annotations

from typing import AbstractSet, Any, Final, Mapping

from app.constants.notification_types import NotificationType
from app.utils.constants import UserRoles


class NotificationRouteRegistryError(KeyError):
    """Unknown event_type for notification routing."""


class NotificationRouteRegistry:
    """Maps notification domain events to SPA paths."""

    _KNOWN: Final[frozenset[str]] = frozenset(
        {
            NotificationType.LEAD_CREATED.value,
            NotificationType.LEAD_OFFLINE_CREATED.value,
            NotificationType.LEAD_MANUAL_CREATED.value,
            NotificationType.LEAD_STATUS_CHANGED.value,
            NotificationType.LEAD_REPLY_ADDED.value,
            NotificationType.LEAD_ACTIVITY_UPDATED.value,
            NotificationType.LEAD_REASSIGN_NEW_ASSIGNEE.value,
            NotificationType.LEAD_REASSIGN_PREVIOUS_ASSIGNEE.value,
            NotificationType.AGENT_APPROVED.value,
            NotificationType.AGENT_REJECTED.value,
            NotificationType.SAVED_SEARCH_CREATED.value,
            NotificationType.PROPERTY_AGENT_ASSIGNED.value,
            NotificationType.PROPERTY_AGENT_UNASSIGNED.value,
            NotificationType.SYSTEM_ANNOUNCEMENT.value,
        }
    )

    @classmethod
    def is_known_event(cls, event_type: str) -> bool:
        return event_type in cls._KNOWN

    @classmethod
    def resolve_action_url(
        cls,
        *,
        event_type: str,
        role_names: AbstractSet[str],
        context: Mapping[str, Any] | None = None,
    ) -> str:
        """Return client deep-link path for this event and recipient role set."""
        if not cls.is_known_event(event_type):
            raise NotificationRouteRegistryError(event_type)

        roles = {str(r) for r in role_names if r is not None}
        ctx = dict(context or {})

        if event_type in {
            NotificationType.LEAD_CREATED.value,
            NotificationType.LEAD_STATUS_CHANGED.value,
            NotificationType.LEAD_REPLY_ADDED.value,
            NotificationType.LEAD_ACTIVITY_UPDATED.value,
        }:
            if UserRoles.ADMIN in roles:
                return cls._admin_lead_path(context=ctx)
            if UserRoles.AGENT in roles:
                return cls._agent_lead_path(context=ctx)
            return cls._registered_user_inquiry_path(context=ctx)

        if event_type in {
            NotificationType.LEAD_OFFLINE_CREATED.value,
            NotificationType.LEAD_MANUAL_CREATED.value,
        }:
            if UserRoles.ADMIN in roles:
                return cls._admin_lead_path(context=ctx)
            if UserRoles.AGENT in roles:
                return cls._agent_lead_path(context=ctx)
            return cls._registered_user_inquiry_path(context=ctx)

        if event_type in {
            NotificationType.LEAD_REASSIGN_NEW_ASSIGNEE.value,
            NotificationType.LEAD_REASSIGN_PREVIOUS_ASSIGNEE.value,
        }:
            return "/agent-dashboard/leads-and-inquiries"

        if event_type in {NotificationType.AGENT_APPROVED.value, NotificationType.AGENT_REJECTED.value}:
            agent_user_id = ctx.get("agent_user_id")
            if not agent_user_id:
                raise NotificationRouteRegistryError(
                    f"{event_type} requires context['agent_user_id'] for routing"
                )
            return f"/agents/{agent_user_id}"

        if event_type == NotificationType.SAVED_SEARCH_CREATED.value:
            if UserRoles.ADMIN in roles:
                return "/admin-dashboard/saved-searches"
            if UserRoles.AGENT in roles:
                return "/agent-saved-searches"
            return "/saved-searches"

        if event_type in {
            NotificationType.PROPERTY_AGENT_ASSIGNED.value,
            NotificationType.PROPERTY_AGENT_UNASSIGNED.value,
        }:
            return "/agent-dashboard/listings"

        if event_type == NotificationType.SYSTEM_ANNOUNCEMENT.value:
            return ctx.get("action_url") or "/"

        raise NotificationRouteRegistryError(event_type)

    @staticmethod
    def _registered_user_inquiry_path(*, context: Mapping[str, Any]) -> str:
        inquiry_id = context.get("inquiry_id") or context.get("entity_id") or context.get("lead_id")
        if inquiry_id:
            return f"/my-inquiries/{inquiry_id}"
        return "/my-inquiries"

    @staticmethod
    def _admin_lead_path(*, context: Mapping[str, Any]) -> str:
        inquiry_id = context.get("inquiry_id") or context.get("entity_id") or context.get("lead_id")
        if inquiry_id:
            return f"/leads/{inquiry_id}"
        return "/leads"

    @staticmethod
    def _agent_lead_path(*, context: Mapping[str, Any]) -> str:
        inquiry_id = context.get("inquiry_id") or context.get("entity_id") or context.get("lead_id")
        if inquiry_id:
            return f"/agent-dashboard/leads/{inquiry_id}"
        return "/agent-dashboard/leads-and-inquiries"
