"""
Step 11: Service tests for AgentService.
Mocks AgentRepository; validates business rules and service/repo interaction.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User
from app.schemas.user import AgentInviteRequest
from app.services.agent_service import AgentService
from app.utils.constants import AgentStatus


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def agent_service(mock_repo) -> AgentService:
    return AgentService(mock_repo)


def test_validate_invite_token_raises_404_when_invite_not_found(agent_service: AgentService):
    """validate_invite_token raises 404 when token is invalid."""
    agent_service._repo.find_invite_by_token_valid.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        agent_service.validate_invite_token("badtoken")
    assert exc_info.value.status_code == 404


def test_validate_invite_token_raises_400_when_invite_used(agent_service: AgentService):
    """validate_invite_token raises 400 when invite already used."""
    invite = MagicMock()
    invite.is_used = True
    agent_service._repo.find_invite_by_token_valid.return_value = invite
    with pytest.raises(HTTPException) as exc_info:
        agent_service.validate_invite_token("usedtoken")
    assert exc_info.value.status_code == 400


def test_get_agent_details_raises_404_when_agent_not_found(agent_service: AgentService):
    """get_agent_details raises 404 when agent_id has no profile."""
    agent_service._repo.get_agent_with_profile.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        agent_service.get_agent_details(uuid.uuid4())
    assert exc_info.value.status_code == 404


def test_list_agents_returns_empty_list_and_zero_when_no_data(agent_service: AgentService):
    """list_agents returns ([], 0) when repo returns no rows."""
    agent_service._repo.list_agents_paginated.return_value = ([], 0)
    agents_data, total = agent_service.list_agents(
        status=None,
        search=None,
        page=1,
        limit=20,
        sort_by="invitedAt",
        sort_order="desc",
    )
    assert agents_data == []
    assert total == 0
    agent_service._repo.list_agents_paginated.assert_called_once()


def test_get_agents_summary_returns_empty_when_no_agents(agent_service: AgentService):
    """get_agents_summary returns empty aggregates and lists; batches repo calls."""
    agent_service._repo.list_all_agents_with_profiles.return_value = []
    agent_service._repo.list_assignments_for_agents.return_value = []
    agent_service._repo.get_latest_invites_for_emails.return_value = {}
    out = agent_service.get_agents_summary()
    assert out == {
        "totalAgents": 0,
        "activeAgents": 0,
        "pendingInvites": 0,
        "pendingReview": 0,
        "declined": 0,
        "lastFiveAgents": [],
    }
    agent_service._repo.list_all_agents_with_profiles.assert_called_once()
    agent_service._repo.list_assignments_for_agents.assert_called_once_with([])
    agent_service._repo.get_latest_invites_for_emails.assert_called_once_with([])


def test_get_agents_summary_profile_counts_and_last_five_by_created_at(agent_service: AgentService):
    """Totals, pendingInvites/pendingReview/declined, and lastFiveAgents follow stored profile.status."""
    uid_a = uuid.uuid4()
    uid_b = uuid.uuid4()
    u_newer = MagicMock()
    u_newer.id = uid_a
    u_newer.email = "newer@example.com"
    u_newer.full_name = "Newer"
    u_newer.is_active = True
    u_newer.created_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    u_newer.cognito_sub = None
    p_newer = MagicMock()
    p_newer.status = AgentStatus.ACTIVE
    p_newer.service_area = None
    p_newer.status_reason = None
    p_newer.decline_reason = None
    p_newer.reviewed_at = None
    p_newer.reviewed_by = None
    p_newer.form_submitted_at = None
    p_newer.password_set_at = None
    p_newer.approved_at = None
    p_newer.approved_by = None

    u_older = MagicMock()
    u_older.id = uid_b
    u_older.email = "older@example.com"
    u_older.full_name = "Older"
    u_older.is_active = False
    u_older.created_at = datetime(2026, 1, 10, tzinfo=timezone.utc)
    u_older.cognito_sub = None
    p_older = MagicMock()
    p_older.status = AgentStatus.INVITED
    p_older.service_area = None
    p_older.status_reason = None
    p_older.decline_reason = None
    p_older.reviewed_at = None
    p_older.reviewed_by = None
    p_older.form_submitted_at = None
    p_older.password_set_at = None
    p_older.approved_at = None
    p_older.approved_by = None

    agent_service._repo.list_all_agents_with_profiles.return_value = [
        (u_older, p_older),
        (u_newer, p_newer),
    ]
    agent_service._repo.list_assignments_for_agents.return_value = []
    agent_service._repo.get_latest_invites_for_emails.return_value = {}

    out = agent_service.get_agents_summary()
    assert out["totalAgents"] == 2
    assert out["activeAgents"] == 1
    assert out["pendingInvites"] == 1
    assert out["pendingReview"] == 0
    assert out["declined"] == 0
    assert len(out["lastFiveAgents"]) == 2
    assert out["lastFiveAgents"][0]["agentId"] == uid_a
    assert out["lastFiveAgents"][1]["agentId"] == uid_b


def test_get_top_agents_leaderboard_formats_response(agent_service: AgentService):
    """get_top_agents_leaderboard maps rows to name, closedDeals, responseRate, area."""
    agent_service._repo.fetch_top_agents_leaderboard_window.return_value = [
        {
            "full_name": "Omar Shdeifat",
            "service_area": "Dabouq",
            "closed_deals": 19,
            "total_inquiries": 50,
            "responded_inquiries": 47,
        }
    ]
    out = agent_service.get_top_agents_leaderboard()
    assert "firstDate" in out and "lastDate" in out
    assert len(out["agents"]) == 1
    assert out["agents"][0]["name"] == "Omar Shdeifat"
    assert out["agents"][0]["closedDeals"] == 19
    assert out["agents"][0]["responseRate"] == "94%"
    assert out["agents"][0]["area"] == "Dabouq"


def test_get_agents_summary_raises_500_on_database_error(agent_service: AgentService):
    """get_agents_summary maps SQLAlchemy errors to HTTP 500."""
    agent_service._repo.list_all_agents_with_profiles.side_effect = SQLAlchemyError(
        "database unavailable"
    )
    with pytest.raises(HTTPException) as exc_info:
        agent_service.get_agents_summary()
    assert exc_info.value.status_code == 500


def test_invite_agent_raises_409_when_user_exists_with_profile(agent_service: AgentService):
    """invite_agent raises 409 when user already exists and has agent profile."""
    user = MagicMock(spec=User)
    user.profile = MagicMock()
    agent_service._repo.get_user_by_email.return_value = user
    with pytest.raises(HTTPException) as exc_info:
        agent_service.invite_agent(
            AgentInviteRequest(email="existing-agent@example.com"),
            current_user=MagicMock(spec=User),
        )
    assert exc_info.value.status_code == 409
