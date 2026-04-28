"""Unit tests for AdminDashboardService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.repositories.admin_dashboard_repository import (
    ActivityLogItem,
    KpiRawSnapshot,
    PropertyPerformanceRow,
    TrendsRaw,
)
from app.schemas.admin_dashboard import PropertyPerformancePeriod
from app.services.admin_dashboard_service import AdminDashboardService, _mom_percent_change


def test_mom_percent_change():
    assert _mom_percent_change(3, 0) == 100.0
    assert _mom_percent_change(0, 0) == 0.0
    assert _mom_percent_change(10, 8) == 25.0


def test_get_kpis_from_repo():
    k = KpiRawSnapshot(
        month_label="2026-01",
        users_curr=10,
        users_prev=8,
        agents_curr=2,
        agents_prev=2,
        listings_curr=5,
        listings_prev=4,
        leads_curr=20,
        leads_prev=10,
        deals_curr=3,
        deals_prev=1,
        pending_approvals=1,
        pending_approvals_today=0,
    )
    repo = MagicMock()
    repo.fetch_kpis.return_value = k
    service = AdminDashboardService(repo)
    out = service.get_kpis("2026-01")
    assert out["month"] == "2026-01"
    assert out["registerUsersMoMDelta"] == 25.0
    assert out["closedDealsThisMonth"] == 3
    assert out["pendingApprovals"] == 1
    repo.fetch_kpis.assert_called_once()


def test_get_trends_from_repo():
    t = TrendsRaw(
        month_labels=["Jan", "Feb"],
        user_growth_series=[1, 2],
        listing_growth_series=[3, 4],
        lead_growth_series=[5, 6],
        months=2,
    )
    repo = MagicMock()
    repo.fetch_trends.return_value = t
    service = AdminDashboardService(repo)
    out = service.get_trends(2, "2026-02")
    assert out["months"] == 2
    assert out["leadGrowthSeries"] == [5, 6]


def test_get_property_performance():
    pid, aid = uuid.uuid4(), uuid.uuid4()
    pr = [
        PropertyPerformanceRow(
            property_id=pid,
            agent_user_id=aid,
            agent_name="A",
            category_name="C",
            type_name="T",
            type_slug="apartment",
            area_or_location="L",
            title="X",
            view_count=9,
        )
    ]
    repo = MagicMock()
    repo.fetch_top_properties_by_views.return_value = (pr, 42)
    service = AdminDashboardService(repo)
    out = service.get_property_performance(
        period=PropertyPerformancePeriod.MONTHLY, page=2, limit=3, agent_id=aid
    )
    assert out["items"][0]["propertyId"] == str(pid)
    assert out["items"][0]["value"] == 9
    assert out["items"][0]["propertyType"] == "apartment"
    assert out["page"] == 2
    assert out["limit"] == 3
    assert out["totalItems"] == 42
    repo.fetch_top_properties_by_views.assert_called_once_with(
        period="monthly", page=2, limit=3, agent_id=aid
    )


def test_get_dashboard_summary_builds_payload():
    k = KpiRawSnapshot(
        month_label="2026-01",
        users_curr=10,
        users_prev=8,
        agents_curr=2,
        agents_prev=2,
        listings_curr=5,
        listings_prev=4,
        leads_curr=20,
        leads_prev=10,
        deals_curr=3,
        deals_prev=1,
        pending_approvals=2,
        pending_approvals_today=1,
    )
    t = TrendsRaw(
        month_labels=["Jan", "Feb"],
        user_growth_series=[1, 2],
        listing_growth_series=[3, 4],
        lead_growth_series=[5, 6],
        months=2,
    )
    pid = uuid.uuid4()
    aid = uuid.uuid4()
    pr = [
        PropertyPerformanceRow(
            property_id=pid,
            agent_user_id=aid,
            agent_name="A",
            category_name="C",
            type_name="T",
            type_slug="villa",
            area_or_location="L",
            title="X",
            view_count=9,
        )
    ]
    repo = MagicMock()
    repo.fetch_kpis = MagicMock(return_value=k)
    repo.fetch_rolling_cumulative_12m_utc.return_value = t
    repo.fetch_lead_source_breakdown.return_value = (["Unspecified", "WhatsApp"], [5, 3])
    repo.fetch_top_properties_by_views.return_value = (pr, 1)
    repo.fetch_total_user_counts_by_role.return_value = {
        "totalRegisterUserCount": 123,
        "totalAdminCount": 7,
    }
    repo.count_active_assigned_agents_for_admin.return_value = 9
    repo.fetch_inherited_admin_ids_for_agent.return_value = []
    repo.fetch_recent_activity_for_user.return_value = [
        ActivityLogItem(text="Did something", tone="info", activity_at=datetime.now(timezone.utc))
    ]
    service = AdminDashboardService(repo)
    current_user = MagicMock()
    current_user.id = uuid.uuid4()
    current_user.roles = []
    out = service.get_dashboard_summary(current_user)
    assert "month" in out
    assert out["totalRegisterUserCount"] == 123
    assert out["totalAdminCount"] == 7
    assert out["totalAgentCount"] == 9
    assert out["registerUsersThisMonth"] == 10
    assert out["leadSourceLabels"] == ["Unspecified", "WhatsApp"]
    assert out["propertyPerformanceSeries"][0]["propertyId"] == str(pid)
    assert out["propertyPerformanceSeries"][0]["agentId"] == str(aid)
    assert "A" in out["propertyPerformanceSeries"][0]["label"]
    assert isinstance(out.get("recentActivity"), list)
    repo.fetch_top_properties_by_views.assert_called_once_with(
        period="monthly", page=1, limit=5, agent_id=None
    )
