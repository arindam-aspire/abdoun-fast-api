"""Notification type registry (Phase 1: in-app only).

Types are stable identifiers stored in the database and used by clients to
render icons/links consistently. Keep these values stable once shipped.
"""

from __future__ import annotations

from enum import Enum


class NotificationType(str, Enum):
    # Leads
    LEAD_CREATED = "lead.created"
    LEAD_ASSIGNED = "lead.assigned"
    LEAD_REASSIGNED = "lead.reassigned"
    LEAD_STATUS_CHANGED = "lead.status_changed"
    LEAD_REPLY_ADDED = "lead.reply_added"

    # Agents
    AGENT_APPROVED = "agent.approved"
    AGENT_REJECTED = "agent.rejected"

    # System / profile
    SYSTEM_ANNOUNCEMENT = "system.announcement"
    PROFILE_UPDATED = "profile.updated"
    FAVORITE_ADDED = "favorite.added"


# Phase 1 rule: system notifications cannot be disabled in preferences.
NON_DISABLEABLE_TYPES: frozenset[str] = frozenset(
    {
        NotificationType.SYSTEM_ANNOUNCEMENT.value,
    }
)

