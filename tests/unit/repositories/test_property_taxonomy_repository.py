"""Unit tests for PropertyTaxonomyRepository."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.property_taxonomy_repository import PropertyTaxonomyRepository


def test_list_active_categories_returns_list() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = PropertyTaxonomyRepository(session)
    result = repo.list_active_categories()
    assert result == []
    session.execute.assert_called_once()


def test_list_active_property_types_no_category_id() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = PropertyTaxonomyRepository(session)
    result = repo.list_active_property_types(category_id=None)
    assert result == []
    session.execute.assert_called_once()


def test_list_active_property_types_with_category_id() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = PropertyTaxonomyRepository(session)
    result = repo.list_active_property_types(category_id=1)
    assert result == []
    session.execute.assert_called_once()

