"""Unit tests for RecentViewRepository property resolution."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.repositories.recent_view_repository import RecentViewRepository


def test_resolve_property_id_prefers_property_id() -> None:
    repo = RecentViewRepository(MagicMock())
    pid = uuid.uuid4()
    resolved = repo.resolve_property_id(property_id=pid, property_hash_id=12345)
    assert resolved == pid


def test_resolve_property_id_uses_hash_when_id_missing() -> None:
    db = MagicMock()
    pid = uuid.uuid4()
    db.execute.return_value.scalar_one_or_none.return_value = pid
    repo = RecentViewRepository(db)
    resolved = repo.resolve_property_id(property_id=None, property_hash_id=987654321)
    assert resolved == pid


def test_resolve_property_id_returns_none_when_both_missing() -> None:
    repo = RecentViewRepository(MagicMock())
    assert repo.resolve_property_id(property_id=None, property_hash_id=None) is None
