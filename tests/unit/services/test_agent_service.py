"""
Step 11: Service tests for AgentService.
Mocks AgentRepository; validates business rules and service/repo interaction.
"""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.schemas.user import AgentInviteRequest
from app.services.agent_service import AgentService


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
