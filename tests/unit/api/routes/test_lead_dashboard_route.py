from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.deps.leads import get_lead_dashboard_service
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app


def _user(role_name: str):
    u = MagicMock()
    u.id = uuid4()
    role = MagicMock()
    role.name = role_name
    role.permissions = []
    u.roles = [role]
    return u


def _fake_db():
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []
    db.execute.return_value = exec_result
    try:
        yield db
    finally:
        pass


def _fake_summary_payload():
    return {
        "totalLeads": 20,
        "newLeads": 8,
        "mql": 5,
        "sql": 3,
        "opportunities": 8,
        "convertedCustomers": 4,
        "averageLeadAgingDays": 6.3,
        "slaBreachCount": 2,
        "conversionRate": 20.0,
        "averageResponseTimeHours": 3.6,
        "funnel": [{"stage": "new", "label": "New", "count": 8}],
        "sourcePerformance": [
            {"source": "EMAIL_FORM", "totalLeads": 12, "converted": 3, "conversionRate": 25.0}
        ],
        "agingBuckets": [{"bucket": "0-1 days", "count": 4}],
        "trend": [{"period": "2026-06-01", "totalLeads": 5, "converted": 1}],
    }


def test_dashboard_summary_route_success() -> None:
    service = MagicMock()
    service.get_dashboard_summary.return_value = _fake_summary_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_dashboard_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/dashboard/summary?range=month")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "Lead dashboard summary fetched successfully"
    assert body["data"]["totalLeads"] == 20
    assert body["data"]["opportunities"] == 8
    service.get_dashboard_summary.assert_called_once()
    app.dependency_overrides.clear()


def test_dashboard_summary_route_defaults_to_month() -> None:
    service = MagicMock()
    service.get_dashboard_summary.return_value = _fake_summary_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("agent")
    app.dependency_overrides[get_lead_dashboard_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/dashboard/summary")
    assert res.status_code == 200
    _, kwargs = service.get_dashboard_summary.call_args
    assert kwargs["range_key"] == "month"
    app.dependency_overrides.clear()


def test_dashboard_summary_route_rejects_invalid_range() -> None:
    service = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_dashboard_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/dashboard/summary?range=decade")
    assert res.status_code == 422
    service.get_dashboard_summary.assert_not_called()
    app.dependency_overrides.clear()


def test_dashboard_summary_route_forbidden_for_registered_user() -> None:
    service = MagicMock()
    service.get_dashboard_summary.side_effect = HTTPException(status_code=403, detail="forbidden")
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_dashboard_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/dashboard/summary?range=week")
    assert res.status_code == 403
    app.dependency_overrides.clear()


def _fake_compliance_payload():
    return {
        "slaBreachCount": 10,
        "slaComplianceRate": 75.0,
        "averageResponseTimeHours": 4.3,
        "followUpComplianceRate": 80.0,
        "missingSourceCount": 2,
        "duplicateCount": 3,
        "missingLostReasonCount": 5,
    }


def test_compliance_report_route_success() -> None:
    service = MagicMock()
    service.get_compliance_report.return_value = _fake_compliance_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_dashboard_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/reports/compliance")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "Lead compliance report fetched successfully"
    assert body["data"]["slaComplianceRate"] == 75.0
    assert body["data"]["missingLostReasonCount"] == 5
    service.get_compliance_report.assert_called_once()
    app.dependency_overrides.clear()


def test_compliance_report_route_forbidden_for_registered_user() -> None:
    service = MagicMock()
    service.get_compliance_report.side_effect = HTTPException(status_code=403, detail="forbidden")
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_dashboard_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/reports/compliance")
    assert res.status_code == 403
    app.dependency_overrides.clear()
