"""Lead notification dispatch service."""

from __future__ import annotations

from app.utils.logger import api_logger


class LeadNotificationService:
    """Creates/dispatches lead notifications after successful actions."""

    def emit_lead_event(
        self,
        *,
        event_type: str,
        lead_id: str,
        actor_user_id: str | None = None,
        message: str | None = None,
    ) -> None:
        # TODO: Wire to notification center module and durable event bus.
        api_logger.info(
            "lead_notification_event type=%s lead_id=%s actor_user_id=%s message=%s",
            event_type,
            lead_id,
            actor_user_id,
            message,
        )

    def emit_email_hook_todo(
        self,
        *,
        event_type: str,
        lead_id: str,
        recipient_hint: str | None = None,
    ) -> None:
        # TODO: Replace with real email adapter when notification module is upgraded.
        api_logger.info(
            "lead_email_todo_hook type=%s lead_id=%s recipient_hint=%s",
            event_type,
            lead_id,
            recipient_hint,
        )
