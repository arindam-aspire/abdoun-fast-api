"""Notification type registry (Phase 1: in-app only).

Types are stable identifiers stored in the database and used by clients to
render icons/links consistently. Keep these values stable once shipped.
"""

from __future__ import annotations

from enum import Enum


class NotificationType(str, Enum):
    # Leads
    LEAD_CREATED = "lead.created"
    LEAD_OFFLINE_CREATED = "lead.offline_created"
    LEAD_MANUAL_CREATED = "lead.manual_created"
    LEAD_STATUS_CHANGED = "lead.status_changed"
    LEAD_REPLY_ADDED = "lead.reply_added"
    LEAD_ACTIVITY_UPDATED = "lead.activity_updated"
    LEAD_REASSIGN_NEW_ASSIGNEE = "lead.reassign_new_assignee"
    LEAD_REASSIGN_PREVIOUS_ASSIGNEE = "lead.reassign_previous_assignee"

    # Agents
    AGENT_APPROVED = "agent.approved"
    AGENT_REJECTED = "agent.rejected"

    # System (reserved; preference layer treats as non-disableable)
    SYSTEM_ANNOUNCEMENT = "system.announcement"
    SAVED_SEARCH_CREATED = "saved_search.created"
    PROPERTY_AGENT_ASSIGNED = "property.agent_assigned"
    PROPERTY_AGENT_UNASSIGNED = "property.agent_unassigned"


# Phase 1 rule: system notifications cannot be disabled in preferences.
NON_DISABLEABLE_TYPES: frozenset[str] = frozenset(
    {
        NotificationType.SYSTEM_ANNOUNCEMENT.value,
    }
)

