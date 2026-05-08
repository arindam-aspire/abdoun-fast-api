"""Notification message templates (Phase 1: in-app only).

Templates are intentionally simple for Phase 1 and stored as constants.
They are built into title/message strings by NotificationTemplateService.
"""

from __future__ import annotations

from app.constants.notification_types import NotificationType


NOTIFICATION_MESSAGES: dict[str, dict[str, str]] = {
    NotificationType.LEAD_CREATED.value: {
        "title": "New Lead Created",
        "message": "A new lead has been created.",
    },
    NotificationType.LEAD_ASSIGNED.value: {
        "title": "New Lead Assigned",
        "message": "A new lead has been assigned to you.",
    },
    NotificationType.LEAD_REASSIGNED.value: {
        "title": "Lead Reassigned",
        "message": "A lead has been reassigned to you.",
    },
    NotificationType.LEAD_STATUS_CHANGED.value: {
        "title": "Lead Status Updated",
        "message": "Lead status has been updated.",
    },
    NotificationType.LEAD_REPLY_ADDED.value: {
        "title": "New Lead Reply",
        "message": "A new reply was added to a lead.",
    },
    NotificationType.AGENT_APPROVED.value: {
        "title": "Agent Approved",
        "message": "Your agent profile has been approved.",
    },
    NotificationType.AGENT_REJECTED.value: {
        "title": "Agent Rejected",
        "message": "Your agent profile has been rejected.",
    },
    NotificationType.SYSTEM_ANNOUNCEMENT.value: {
        "title": "System Announcement",
        "message": "There is a new system announcement.",
    },
    NotificationType.PROFILE_UPDATED.value: {
        "title": "Profile Updated",
        "message": "Your profile has been updated successfully.",
    },
    NotificationType.FAVORITE_ADDED.value: {
        "title": "Property Added to Favorites",
        "message": "Property #{property_hash} has been added to your favorites.",
    },
}

