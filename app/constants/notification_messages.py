"""Notification message templates (in-app).

Templates are built by NotificationTemplateService after strict validation.
"""

from __future__ import annotations

from app.constants.notification_types import NotificationType


NOTIFICATION_MESSAGES: dict[str, dict[str, str]] = {
    NotificationType.LEAD_CREATED.value: {
        "title": "New Lead Created",
        "message": "{lead_name} — Lead ID: {lead_id}. Created by: {creator_name}.",
    },
    NotificationType.LEAD_OFFLINE_CREATED.value: {
        "title": "Offline Lead Created",
        "message": "{lead_name} — Lead ID: {lead_id}. Created by: {creator_name}.",
    },
    NotificationType.LEAD_MANUAL_CREATED.value: {
        "title": "Lead Created",
        "message": "{lead_name} — Lead ID: {lead_id}. Created by: {creator_name}.",
    },
    NotificationType.LEAD_STATUS_CHANGED.value: {
        "title": "Lead Status Updated",
        "message": "{lead_name} — Lead ID: {lead_id}. Status {previous_status} → {new_status}. Updated by {actor_name}.",
    },
    NotificationType.LEAD_REPLY_ADDED.value: {
        "title": "New Lead Reply",
        "message": "{lead_name} — Lead ID: {lead_id}. New message from {sender_name}.",
    },
    NotificationType.LEAD_ACTIVITY_UPDATED.value: {
        "title": "Update on your inquiry",
        "message": "{lead_name} — Lead ID: {lead_id}. {sender_name} added an update to your lead.",
    },
    NotificationType.LEAD_REASSIGN_NEW_ASSIGNEE.value: {
        "title": "Lead Assigned",
        "message": "{lead_name} — Lead ID: {lead_id}. Assigned by {admin_name}.",
    },
    NotificationType.LEAD_REASSIGN_PREVIOUS_ASSIGNEE.value: {
        "title": "Lead Unassigned",
        "message": "{lead_name} — Lead ID: {lead_id}. Updated by {admin_name}.",
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
    NotificationType.SAVED_SEARCH_CREATED.value: {
        "title": "Saved Search Created",
        "message": "{search_name} — Created by {creator_name}.",
    },
    NotificationType.PROPERTY_AGENT_ASSIGNED.value: {
        "title": "Property Assigned",
        "message": "{property_name} — Property ID: {property_id}. Assigned by {admin_name}.",
    },
    NotificationType.PROPERTY_AGENT_UNASSIGNED.value: {
        "title": "Property Unassigned",
        "message": "{property_name} — Property ID: {property_id}. Updated by {admin_name}.",
    },
}
