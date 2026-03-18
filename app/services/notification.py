"""Notification service: agent approved/rejected/invite; log for now, wire to SES/email in production."""

from typing import Optional

from app.utils.logger import api_logger
from app.utils.log_messages import LogMessages, format_log_message


def notify_agent_approved(agent_email: str, agent_full_name: str) -> None:
    """Notify agent that they have been approved. In production: send email (e.g. SES)."""
    api_logger.info(
        format_log_message(
            LogMessages.Notification.AGENT_APPROVED,
            email=agent_email,
            name=agent_full_name,
        )
    )
    # TODO: e.g. ses_client.send_email(Source=..., Destinations=[agent_email], ...)


def notify_agent_rejected(agent_email: str, agent_full_name: str, decline_reason: Optional[str] = None) -> None:
    """Notify agent that their application was rejected. In production: send email with reason."""
    api_logger.info(
        format_log_message(
            LogMessages.Notification.AGENT_REJECTED,
            email=agent_email,
            name=agent_full_name,
        )
    )
    if decline_reason:
        api_logger.info(
            format_log_message(
                LogMessages.Notification.DECLINE_REASON,
                decline_reason=decline_reason,
            )
        )
    # TODO: send email with decline_reason


def notify_agent_invite_sent(invite_email: str, invite_link: str, invited_by_email: str) -> None:
    """Notify invitee that they received an agent invite. In production: send email with link."""
    api_logger.info(
        format_log_message(
            LogMessages.Notification.INVITE_SENT,
            to_email=invite_email,
            link=invite_link,
            by_email=invited_by_email,
        )
    )
    # TODO: send email with invite_link
