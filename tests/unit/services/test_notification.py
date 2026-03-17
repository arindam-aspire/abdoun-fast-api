"""Unit tests for app.services.notification."""
from unittest.mock import patch

import pytest

from app.services import notification


def test_notify_agent_approved():
    with patch.object(notification.api_logger, "info") as mock_info:
        notification.notify_agent_approved("agent@example.com", "Agent Name")
        mock_info.assert_called_once()
        call_args = str(mock_info.call_args)
        assert "agent@example.com" in call_args or "Agent Name" in call_args


def test_notify_agent_rejected_without_reason():
    with patch.object(notification.api_logger, "info") as mock_info:
        notification.notify_agent_rejected("agent@example.com", "Agent Name")
        assert mock_info.call_count == 1


def test_notify_agent_rejected_with_reason():
    with patch.object(notification.api_logger, "info") as mock_info:
        notification.notify_agent_rejected(
            "agent@example.com",
            "Agent Name",
            decline_reason="Incomplete profile",
        )
        assert mock_info.call_count >= 2
        calls = [str(c) for c in mock_info.call_args_list]
        assert any("Incomplete profile" in c for c in calls)


def test_notify_agent_invite_sent():
    with patch.object(notification.api_logger, "info") as mock_info:
        notification.notify_agent_invite_sent(
            "invitee@example.com",
            "https://example.com/invite/abc",
            "admin@example.com",
        )
        mock_info.assert_called_once()
