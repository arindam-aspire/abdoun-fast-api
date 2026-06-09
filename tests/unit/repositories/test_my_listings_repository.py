"""Unit tests for PropertyRepository.list_my_listings scope filters."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.repositories.property_repository import PropertyRepository


def test_list_my_listings_agent_scope_builds_query() -> None:
    db = MagicMock()
    repo = PropertyRepository(db)
    agent_id = uuid.uuid4()

    # Execute chain returns empty result set
    db.execute.return_value.scalar.return_value = 0
    db.execute.return_value.unique.return_value.scalars.return_value.all.return_value = []

    rows, total, subs = repo.list_my_listings(
        scope="agent",
        agent_user_id=agent_id,
        page=1,
        page_size=10,
    )

    assert rows == []
    assert total == 0
    assert subs == {}
    assert db.execute.called


def test_list_my_listings_admin_scope_no_agent_filter() -> None:
    db = MagicMock()
    repo = PropertyRepository(db)
    db.execute.return_value.scalar.return_value = 0
    db.execute.return_value.unique.return_value.scalars.return_value.all.return_value = []

    _, total, _ = repo.list_my_listings(
        scope="admin",
        agent_user_id=None,
        page=1,
        page_size=10,
        status="active",
        property_type="villa",
        search="test",
    )

    assert total == 0
    assert db.execute.called
