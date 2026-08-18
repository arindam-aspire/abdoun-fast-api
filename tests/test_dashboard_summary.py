from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.dashboard import DashboardSummaryResponse
from app.services import dashboard as dashboard_service


def _stub_repository(monkeypatch, *, pending_agents: int = 2) -> None:
    monkeypatch.setattr(
        dashboard_service,
        "get_user_counts",
        lambda *_args, **_kwargs: {
            "total_users": 20,
            "total_agents": 5,
            "total_admins": 2,
            "users_current": 6,
            "users_previous": 4,
            "agents_current": 1,
            "agents_previous": 2,
            "pending_agents": pending_agents,
            "pending_agents_today": 1,
        },
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_listing_counts",
        lambda *_args, **_kwargs: {
            "current": 9,
            "previous": 3,
            "pending": 4,
            "pending_today": 2,
        },
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_lead_counts",
        lambda *_args, **_kwargs: {"current": 12, "previous": 8},
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_user_growth",
        lambda *_args, **_kwargs: [(datetime(2026, 7, 1), 6)],
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_listing_growth",
        lambda *_args, **_kwargs: [(datetime(2025, 8, 1), 2), (datetime(2026, 7, 1), 9)],
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_lead_growth",
        lambda *_args, **_kwargs: [(datetime(2026, 7, 1), 12)],
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_lead_sources",
        lambda *_args, **_kwargs: [("WHATSAPP", 3), ("EMAIL_FORM", 7)],
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_closed_deals_count",
        lambda *_args, **_kwargs: 3,
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_recent_activity",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                id=uuid4(),
                activity_type="deal_closure_approved",
                message="Deal approved",
                tone=None,
                created_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            )
        ],
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_health_context",
        lambda *_args, **_kwargs: (
            SimpleNamespace(
                full_name="Dashboard User",
                phone_number="+962700000000",
                is_email_verified=True,
                is_phone_verified=True,
            ),
            SimpleNamespace(
                identity_document_s3_link="s3://identity",
                service_area="Amman",
            ),
            SimpleNamespace(legal_document_s3_link="s3://legal"),
        ),
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_pending_agency_counts",
        lambda *_args, **_kwargs: (3, 1),
    )


def test_dashboard_summary_aligns_series_and_calculates_deltas(monkeypatch) -> None:
    _stub_repository(monkeypatch)

    data = dashboard_service.dashboard_summary(
        MagicMock(),
        user_id=uuid4(),
        roles=("super_admin",),
        agency_id=None,
        now=datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
    )
    payload = data.model_dump(by_alias=True)

    assert payload["month"] == "2026-07"
    assert payload["monthLabels"] == [
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
    ]
    assert payload["registerUsersMoMDelta"] == 50.0
    assert payload["agentsMoMDelta"] == -50.0
    assert payload["listingsMoMDelta"] == 200.0
    assert payload["leadsMoMDelta"] == 50.0
    assert payload["userGrowthSeries"] == [0] * 11 + [6]
    assert payload["listingGrowthSeries"] == [2] + [0] * 10 + [9]
    assert payload["leadSourceLabels"] == ["EMAIL_FORM", "WHATSAPP"]
    assert payload["leadSourceValues"] == [7, 3]
    assert payload["pendingApprovals"] == 3
    assert payload["pendingApprovalsToday"] == 1
    assert payload["recentActivity"][0]["type"] == "approval"
    assert payload["recentActivity"][0]["tone"] == "success"
    assert payload["healthAlerts"] == ["PENDING_APPROVALS"]


def test_agent_summary_does_not_expose_pending_approval_counts(monkeypatch) -> None:
    _stub_repository(monkeypatch)

    data = dashboard_service.dashboard_summary(
        MagicMock(),
        user_id=uuid4(),
        roles=("agent",),
        agency_id=uuid4(),
        now=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )

    assert data.pending_approvals == 0
    assert data.pending_approvals_today == 0
    assert "PENDING_APPROVALS" not in data.health_alerts


def test_response_envelope_has_exact_required_shape(monkeypatch) -> None:
    _stub_repository(monkeypatch)
    data = dashboard_service.dashboard_summary(
        MagicMock(),
        user_id=uuid4(),
        roles=("admin",),
        agency_id=uuid4(),
        now=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )

    payload = DashboardSummaryResponse(data=data).model_dump(by_alias=True)

    assert set(payload) == {"success", "message", "data", "meta"}
    assert payload["success"] is True
    assert payload["message"] == "Dashboard summary retrieved successfully"
    assert payload["meta"] is None


def test_scope_precedence_and_role_restriction() -> None:
    user_id = uuid4()
    agency_id = uuid4()

    assert dashboard_service._scope_for_context(
        user_id=user_id,
        roles=("agent", "admin"),
        agency_id=agency_id,
    ).kind == "agency_admin"
    assert dashboard_service._scope_for_context(
        user_id=user_id,
        roles=("super_admin", "admin"),
        agency_id=agency_id,
    ).kind == "super_admin"

    with pytest.raises(HTTPException) as exc:
        dashboard_service._scope_for_context(
            user_id=user_id,
            roles=("registered_user",),
            agency_id=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [(0, 0, 0.0), (4, 0, 100.0), (3, 6, -50.0)],
)
def test_mom_zero_convention(current, previous, expected) -> None:
    assert dashboard_service._mom_delta(current, previous) == expected
