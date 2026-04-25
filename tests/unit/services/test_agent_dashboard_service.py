"""Unit tests for AgentDashboardService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.repositories.agent_dashboard_repository import ActivityLogItem, DashboardSummaryMetrics
from app.services.agent_dashboard_service import AgentDashboardService
from app.utils.status_codes import HTTPStatus


def _make_user(*, roles: list[str]):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.roles = [MagicMock(name="role") for _ in roles]
    for role_obj, role_name in zip(user.roles, roles):
        role_obj.name = role_name
    return user


def test_dashboard_service_denies_non_agent_user():
    repo = MagicMock()
    service = AgentDashboardService(repo)
    user = _make_user(roles=["registered_user"])

    with pytest.raises(HTTPException) as exc:
        service.get_dashboard_summary(user)

    assert exc.value.status_code == HTTPStatus.FORBIDDEN
    repo.get_metrics.assert_not_called()


def test_mom_percent_edge_previous_zero_current_positive():
    assert AgentDashboardService._mom_percent_change(3, 0) == 100.0
    assert AgentDashboardService._mom_percent_change(0, 0) == 0.0


def test_dashboard_service_returns_payload_for_agent():
    repo = MagicMock()
    repo.get_metrics.return_value = DashboardSummaryMetrics(
        total_properties=11,
        active_properties=7,
        draft_properties=0,
        leads_this_month=20,
        deal_close_count=3,
        inquiry_volume_all_time=20,
        inquiry_volume_last_7_days=8,
        total_property_views=542,
        inquiry_trend_last_30_days=[0] * 30,
        recent_activity=[
            ActivityLogItem(
                text="New inquiry on Villa Abdoun, 4BR.",
                tone="success",
                activity_at=datetime.now(timezone.utc),
            )
        ],
        listings_mtd_current=6,
        listings_mtd_previous=5,
        leads_mtd_current=20,
        leads_mtd_previous=25,
        deals_mtd_current=2,
        deals_mtd_previous=2,
        views_mtd_current=100,
        views_mtd_previous=80,
    )
    service = AgentDashboardService(repo)
    user = _make_user(roles=["agent"])

    data = service.get_dashboard_summary(user)

    repo.get_metrics.assert_called_once()
    call_kwargs = repo.get_metrics.call_args.kwargs
    assert call_kwargs["agent_ids"] == [user.id]

    assert data["totalProperties"] == 11
    assert data["conversionRate"] == 15
    assert len(data["inquiryTrendLast30Days"]) == 30
    assert data["recentActivity"][0]["tone"] == "success"
    assert data["listingsChangePercent"] == 20.0
    assert data["leadsChangePercent"] == -20.0
    assert data["dealsClosedChangePercent"] == 0.0
    assert data["propertyViewsChangePercent"] == 25.0

