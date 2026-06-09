from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.repositories.lead_dashboard_repository import LeadComplianceMetrics, LeadDashboardMetrics
from app.services.lead_dashboard_service import LeadDashboardService


def _user_with_role(role: str):
    u = MagicMock()
    u.id = uuid4()
    role_obj = MagicMock()
    role_obj.name = role
    u.roles = [role_obj]
    return u


def _metrics() -> LeadDashboardMetrics:
    return LeadDashboardMetrics(
        total_leads=20,
        status_counts={
            "NEW": 8,
            "IN_PROGRESS": 5,
            "REQUEST_FOR_CLOSE": 3,
            "CLOSED": 4,
        },
        avg_aging_days=6.27,
        avg_response_hours=3.55,
        sla_breach_count=2,
        source_performance=[
            {"source": "EMAIL_FORM", "total_leads": 12, "converted": 3},
            {"source": "PHONE", "total_leads": 8, "converted": 1},
        ],
        aging_buckets={"0-1 days": 4, "4-7 days": 6},
        trend=[
            {"period": "2026-06-01", "total_leads": 5, "converted": 1},
            {"period": "2026-06-02", "total_leads": 7, "converted": 2},
        ],
    )


def _build_service(metrics: LeadDashboardMetrics | None = None) -> tuple[LeadDashboardService, MagicMock]:
    repo = MagicMock()
    repo.get_metrics.return_value = metrics or _metrics()
    return LeadDashboardService(repo), repo


def test_admin_scope_builds_full_payload() -> None:
    service, repo = _build_service()
    actor = _user_with_role("admin")

    out = service.get_dashboard_summary(actor=actor, range_key="month")

    repo.get_metrics.assert_called_once_with(scope="admin", range_key="month", actor_id=None)
    assert out["totalLeads"] == 20
    assert out["newLeads"] == 8
    assert out["mql"] == 5
    assert out["sql"] == 3
    assert out["opportunities"] == 8  # IN_PROGRESS + REQUEST_FOR_CLOSE
    assert out["convertedCustomers"] == 4
    assert out["conversionRate"] == 20.0  # 4 / 20 * 100
    assert out["averageLeadAgingDays"] == 6.3
    assert out["averageResponseTimeHours"] == 3.6
    assert out["slaBreachCount"] == 2


def test_funnel_stages_in_order() -> None:
    service, _ = _build_service()
    out = service.get_dashboard_summary(actor=_user_with_role("admin"), range_key="week")

    stages = [stage["stage"] for stage in out["funnel"]]
    assert stages == ["new", "mql", "sql", "opportunities", "converted"]
    by_stage = {s["stage"]: s["count"] for s in out["funnel"]}
    assert by_stage["opportunities"] == 8
    assert by_stage["converted"] == 4


def test_source_performance_conversion_rate() -> None:
    service, _ = _build_service()
    out = service.get_dashboard_summary(actor=_user_with_role("admin"), range_key="month")

    email = next(s for s in out["sourcePerformance"] if s["source"] == "EMAIL_FORM")
    assert email["conversionRate"] == 25.0  # 3 / 12 * 100


def test_aging_buckets_are_gap_filled_and_ordered() -> None:
    service, _ = _build_service()
    out = service.get_dashboard_summary(actor=_user_with_role("admin"), range_key="month")

    labels = [b["bucket"] for b in out["agingBuckets"]]
    assert labels == ["0-1 days", "2-3 days", "4-7 days", "8-14 days", "15-30 days", "31+ days"]
    counts = {b["bucket"]: b["count"] for b in out["agingBuckets"]}
    assert counts["0-1 days"] == 4
    assert counts["4-7 days"] == 6
    assert counts["2-3 days"] == 0


def test_agent_scope_passes_actor_id() -> None:
    service, repo = _build_service()
    actor = _user_with_role("agent")

    service.get_dashboard_summary(actor=actor, range_key="day")

    repo.get_metrics.assert_called_once_with(scope="agent", range_key="day", actor_id=actor.id)


def test_registered_user_is_forbidden() -> None:
    service, _ = _build_service()
    with pytest.raises(HTTPException) as exc:
        service.get_dashboard_summary(actor=_user_with_role("registered_user"), range_key="month")
    assert exc.value.status_code == 403


def test_invalid_range_raises_400() -> None:
    service, _ = _build_service()
    with pytest.raises(HTTPException) as exc:
        service.get_dashboard_summary(actor=_user_with_role("admin"), range_key="decade")
    assert exc.value.status_code == 400


def test_zero_total_yields_zero_conversion_rate() -> None:
    empty = LeadDashboardMetrics(total_leads=0, status_counts={})
    service, _ = _build_service(empty)
    out = service.get_dashboard_summary(actor=_user_with_role("admin"), range_key="year")
    assert out["conversionRate"] == 0.0
    assert out["totalLeads"] == 0
    assert len(out["funnel"]) == 5


def _compliance_metrics() -> LeadComplianceMetrics:
    return LeadComplianceMetrics(
        total_leads=40,
        sla_breach_count=10,
        avg_response_hours=4.27,
        active_total=25,
        follow_up_compliant=20,
        missing_source_count=2,
        duplicate_count=3,
        missing_lost_reason_count=5,
    )


def _build_compliance_service(
    metrics: LeadComplianceMetrics | None = None,
) -> tuple[LeadDashboardService, MagicMock]:
    repo = MagicMock()
    repo.get_compliance_metrics.return_value = metrics or _compliance_metrics()
    return LeadDashboardService(repo), repo


def test_compliance_admin_scope_builds_payload() -> None:
    service, repo = _build_compliance_service()
    actor = _user_with_role("admin")

    out = service.get_compliance_report(actor=actor)

    repo.get_compliance_metrics.assert_called_once_with(scope="admin", actor_id=None)
    assert out["slaBreachCount"] == 10
    assert out["slaComplianceRate"] == 75.0  # (40 - 10) / 40 * 100
    assert out["averageResponseTimeHours"] == 4.3
    assert out["followUpComplianceRate"] == 80.0  # 20 / 25 * 100
    assert out["missingSourceCount"] == 2
    assert out["duplicateCount"] == 3
    assert out["missingLostReasonCount"] == 5


def test_compliance_agent_scope_passes_actor_id() -> None:
    service, repo = _build_compliance_service()
    actor = _user_with_role("agent")

    service.get_compliance_report(actor=actor)

    repo.get_compliance_metrics.assert_called_once_with(scope="agent", actor_id=actor.id)


def test_compliance_registered_user_is_forbidden() -> None:
    service, _ = _build_compliance_service()
    with pytest.raises(HTTPException) as exc:
        service.get_compliance_report(actor=_user_with_role("registered_user"))
    assert exc.value.status_code == 403


def test_compliance_zero_leads_yields_zero_rates() -> None:
    service, _ = _build_compliance_service(LeadComplianceMetrics())
    out = service.get_compliance_report(actor=_user_with_role("admin"))
    assert out["slaComplianceRate"] == 0.0
    assert out["followUpComplianceRate"] == 0.0
    assert out["duplicateCount"] == 0
