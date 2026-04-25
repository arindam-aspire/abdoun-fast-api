"""Unit tests for admin dashboard repository helpers."""

import pytest

from app.repositories.admin_dashboard_repository import _property_performance_time_filter_sql
from app.schemas.admin_dashboard import PropertyPerformancePeriod


@pytest.mark.parametrize(
    "period,expected_substr",
    [
        ("all", ""),
        ("weekly", "NOW() - interval '7 days'"),
        ("monthly", "NOW() - interval '30 days'"),
        ("yearly", "NOW() - interval '365 days'"),
    ],
)
def test_property_performance_time_filter_sql(period: str, expected_substr: str) -> None:
    out = _property_performance_time_filter_sql(period)
    if expected_substr:
        assert expected_substr in out
        assert "pv.viewed_at >=" in out
        assert "AT TIME ZONE" not in out
    else:
        assert out == ""


def test_property_performance_time_filter_sql_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Invalid property performance period"):
        _property_performance_time_filter_sql("decade")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("all", PropertyPerformancePeriod.ALL),
        ("weekly", PropertyPerformancePeriod.WEEKLY),
        ("WEEKLY", PropertyPerformancePeriod.WEEKLY),
        ("  Monthly ", PropertyPerformancePeriod.MONTHLY),
        ("YeArLy", PropertyPerformancePeriod.YEARLY),
    ],
)
def test_property_performance_period_case_insensitive(raw: str, expected: PropertyPerformancePeriod) -> None:
    assert PropertyPerformancePeriod(raw) is expected


def test_property_performance_period_invalid_raises() -> None:
    with pytest.raises(ValueError):
        PropertyPerformancePeriod("decade")
