"""Unit tests for LocationRepository."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.location_repository import LocationRepository


def test_list_active_cities_returns_list() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = LocationRepository(session)
    result = repo.list_active_cities()
    assert result == []
    session.execute.assert_called_once()


def test_list_active_areas_no_city_name() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = LocationRepository(session)
    result = repo.list_active_areas(city_name=None)
    assert result == []


def test_list_active_areas_with_city_name() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = LocationRepository(session)
    result = repo.list_active_areas(city_name="Paris")
    assert result == []
    session.execute.assert_called_once()
