"""
Step 10: Repository tests for AgentRepository.
Uses mocked DB session so no database is required; verifies method behaviour and return types.
"""
import uuid
from unittest.mock import MagicMock

import pytest

from app.repositories.agent_repository import AgentRepository


@pytest.fixture
def mock_session():
    """Mock SQLAlchemy session."""
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.scalar.return_value = 0
    session.execute.return_value.first.return_value = None
    session.execute.return_value.all.return_value = []
    session.execute.return_value.unique.return_value.scalars.return_value.all.return_value = []
    return session


@pytest.fixture
def agent_repo(mock_session) -> AgentRepository:
    return AgentRepository(mock_session)


def test_get_user_by_email_returns_none_when_empty(agent_repo: AgentRepository):
    """get_user_by_email returns None when no user exists."""
    assert agent_repo.get_user_by_email("nobody@example.com") is None


def test_get_role_by_name_returns_none_when_empty(agent_repo: AgentRepository):
    """get_role_by_name returns None when no role exists."""
    assert agent_repo.get_role_by_name("admin") is None


def test_get_agent_with_profile_returns_none_for_unknown_id(agent_repo: AgentRepository):
    """get_agent_with_profile returns None for non-existent agent_id."""
    assert agent_repo.get_agent_with_profile(uuid.uuid4()) is None


def test_find_invite_by_token_valid_returns_none_when_empty(agent_repo: AgentRepository):
    """find_invite_by_token_valid returns None when no invite exists."""
    assert agent_repo.find_invite_by_token_valid("sometoken") is None


def test_list_agents_paginated_returns_empty_list_and_zero_total(agent_repo: AgentRepository):
    """list_agents_paginated returns ([], 0) when no data."""
    rows, total = agent_repo.list_agents_paginated(
        status=None,
        search=None,
        sort_by="invitedAt",
        sort_order="desc",
        page=1,
        limit=10,
    )
    assert rows == []
    assert total == 0


def test_list_all_agents_with_profiles_returns_empty_when_no_data(agent_repo: AgentRepository):
    """list_all_agents_with_profiles returns [] when no data."""
    assert agent_repo.list_all_agents_with_profiles() == []


def test_list_assignments_for_agents_returns_empty_when_no_ids(agent_repo: AgentRepository):
    """list_assignments_for_agents returns [] when agent_ids is empty."""
    assert agent_repo.list_assignments_for_agents([]) == []


def test_get_latest_invites_for_emails_returns_empty_dict_when_no_emails(agent_repo: AgentRepository):
    """get_latest_invites_for_emails returns {} when emails is empty."""
    assert agent_repo.get_latest_invites_for_emails([]) == {}


def test_fetch_top_agents_leaderboard_window_returns_empty(agent_repo: AgentRepository):
    """fetch_top_agents_leaderboard_window returns [] when SQL returns no rows."""
    from datetime import datetime, timezone

    result_proxy = MagicMock()
    result_proxy.mappings.return_value.all.return_value = []
    agent_repo._db.execute.return_value = result_proxy
    out = agent_repo.fetch_top_agents_leaderboard_window(
        period_start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 3, 31, tzinfo=timezone.utc),
        limit=10,
    )
    assert out == []


def test_list_invites_by_inviter_returns_empty_list(agent_repo: AgentRepository):
    """list_invites_by_inviter returns [] when no invites."""
    result = agent_repo.list_invites_by_inviter(uuid.uuid4())
    assert result == []


def test_get_status_by_emails_returns_empty_dict(agent_repo: AgentRepository):
    """get_status_by_emails returns {} when no emails given."""
    assert agent_repo.get_status_by_emails([]) == {}


def test_list_assignments_returns_empty_list(agent_repo: AgentRepository):
    """list_assignments returns [] when no assignments."""
    result = agent_repo.list_assignments(agent_id=None, admin_id=uuid.uuid4())
    assert result == []


def test_commit_rollback_refresh_can_be_called(agent_repo: AgentRepository):
    """Transaction helpers do not raise."""
    agent_repo.commit()
    agent_repo.rollback()
    agent_repo.refresh(MagicMock())
