"""Tests for resolving free-text serviceArea labels into area rows."""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.live_schema import Area, City
from app.services.agents import (
    _resolve_area_ids_from_service_area_label,
    _service_area_label,
)


def _area_id(db, area_name: str, city_name: str = "Amman") -> int:
    area_id = db.execute(
        select(Area.id)
        .join(City, City.id == Area.city_id)
        .where(Area.name == area_name, City.name == city_name)
    ).scalar_one()
    return int(area_id)


def test_resolve_area_ids_from_area_city_label() -> None:
    db = SessionLocal()
    try:
        expected = [
            _area_id(db, "2nd Circle"),
            _area_id(db, "5th Circle"),
            _area_id(db, "Al Abdali"),
        ]
        label = "2nd Circle, Amman, 5th Circle, Amman, Al Abdali, Amman"
        assert _resolve_area_ids_from_service_area_label(db, label) == expected
    finally:
        db.close()


def test_resolve_area_ids_preserves_selection_order() -> None:
    db = SessionLocal()
    try:
        expected = [_area_id(db, "Al Abdali"), _area_id(db, "1st Circle")]
        label = "Al Abdali, Amman, 1st Circle, Amman"
        assert _resolve_area_ids_from_service_area_label(db, label) == expected
    finally:
        db.close()


def test_service_area_label_includes_city_name() -> None:
    label = _service_area_label(
        [
            {"id": 19, "name": "2nd Circle", "cityId": 1, "cityName": "Amman"},
            {"id": 27, "name": "5th Circle", "cityId": 1, "cityName": "Amman"},
        ]
    )
    assert label == "2nd Circle, Amman, 5th Circle, Amman"
