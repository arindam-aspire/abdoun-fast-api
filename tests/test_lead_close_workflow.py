from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.live_schema import Lead, LeadCloseRequest, LeadStatusHistory
from app.services import deal_closures as deal_closure_service
from app.services import leads as lead_service


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _lead(*, status: str = "IN_PROGRESS", assigned_agent_id=None) -> Lead:
    return Lead(
        id=uuid4(),
        property_id=None,
        user_id=uuid4(),
        status=status,
        source="EMAIL_FORM",
        assigned_agent_id=assigned_agent_id,
        lead_number="LD-TEST-00001",
        communication_mode="IN_APP",
    )


@pytest.mark.parametrize(
    ("roles", "assigned", "allowed"),
    [
        (("agent",), True, True),
        (("agent",), False, False),
        (("admin",), True, False),
        (("super_admin",), True, False),
        (("owner",), True, False),
        (("registered_user",), True, False),
        (("agent", "admin"), True, False),
    ],
)
def test_only_assigned_agent_role_can_request_close(roles, assigned, allowed) -> None:
    actor_id = uuid4()
    lead = _lead(assigned_agent_id=actor_id if assigned else uuid4())

    if allowed:
        lead_service.assert_assigned_agent_can_request_close(lead, user_id=actor_id, roles=roles)
    else:
        with pytest.raises(HTTPException) as exc:
            lead_service.assert_assigned_agent_can_request_close(lead, user_id=actor_id, roles=roles)
        assert exc.value.status_code == 403


@pytest.mark.parametrize("roles", [("agent",), ("owner",), ("registered_user",)])
def test_non_admin_roles_cannot_review_close(roles) -> None:
    with pytest.raises(HTTPException) as exc:
        lead_service.assert_admin_can_review_close(
            MagicMock(),
            _lead(),
            actor_roles=roles,
            actor_agency_id=uuid4(),
        )
    assert exc.value.status_code == 403


def test_super_admin_can_review_close_without_agency() -> None:
    lead_service.assert_admin_can_review_close(
        MagicMock(),
        _lead(),
        actor_roles=("super_admin",),
        actor_agency_id=None,
    )


def test_agency_admin_must_match_lead_agency(monkeypatch) -> None:
    monkeypatch.setattr(lead_service, "lead_belongs_to_agency", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        lead_service.assert_admin_can_review_close(
            MagicMock(),
            _lead(),
            actor_roles=("admin",),
            actor_agency_id=uuid4(),
        )
    assert exc.value.status_code == 403


def test_agency_admin_can_review_lead_in_same_agency(monkeypatch) -> None:
    monkeypatch.setattr(lead_service, "lead_belongs_to_agency", lambda *_args: True)
    lead_service.assert_admin_can_review_close(
        MagicMock(),
        _lead(),
        actor_roles=("admin",),
        actor_agency_id=uuid4(),
    )


def test_request_close_updates_status_and_audit_in_one_transaction() -> None:
    actor_id = uuid4()
    lead = _lead(assigned_agent_id=actor_id)
    db = MagicMock()
    db.execute.side_effect = [_result(lead), _result(None)]
    added = []
    db.add.side_effect = added.append

    request = lead_service.create_lead_close_request(
        db,
        lead=lead,
        requested_by=actor_id,
        actor_roles=("agent",),
        reason="Work completed",
    )

    assert lead.status == "REQUEST_FOR_CLOSE"
    assert lead.request_close_at is not None
    assert request.status == "PENDING"
    histories = [item for item in added if isinstance(item, LeadStatusHistory)]
    assert len(histories) == 1
    assert histories[0].actor_user_id == actor_id
    assert histories[0].to_status == "REQUEST_FOR_CLOSE"
    db.flush.assert_called_once()


def test_duplicate_request_is_idempotently_rejected_with_conflict() -> None:
    actor_id = uuid4()
    lead = _lead(assigned_agent_id=actor_id)
    pending = LeadCloseRequest(id=uuid4(), lead_id=lead.id, requested_by=actor_id, status="PENDING")
    db = MagicMock()
    db.execute.side_effect = [_result(lead), _result(pending)]

    with pytest.raises(HTTPException) as exc:
        lead_service.create_lead_close_request(
            db,
            lead=lead,
            requested_by=actor_id,
            actor_roles=("agent",),
        )

    assert exc.value.status_code == 409
    assert lead.status == "IN_PROGRESS"
    db.flush.assert_not_called()


def test_close_requires_pending_request() -> None:
    db = MagicMock()
    db.execute.return_value = _result(None)
    with pytest.raises(HTTPException) as exc:
        lead_service.get_pending_lead_close_request(db, lead_id=uuid4())
    assert exc.value.status_code == 409


def test_direct_close_without_workflow_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        lead_service.update_lead_status(
            MagicMock(),
            lead=_lead(),
            status="CLOSED",
            actor_user_id=uuid4(),
            actor_roles=("super_admin",),
        )
    assert exc.value.status_code == 409


def test_transition_query_uses_row_lock() -> None:
    db = MagicMock()
    db.execute.return_value = _result(None)
    with pytest.raises(HTTPException):
        lead_service.get_lead_for_update_or_404(db, uuid4())

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


@pytest.mark.parametrize(
    ("approved", "expected_status", "expected_request_status"),
    [(True, "CLOSED", "APPROVED"), (False, "IN_PROGRESS", "REJECTED")],
)
def test_admin_review_resolves_pending_request_atomically(approved, expected_status, expected_request_status) -> None:
    actor_id = uuid4()
    lead = _lead(status="REQUEST_FOR_CLOSE")
    lead.request_close_at = lead_service.utc_now()
    request = LeadCloseRequest(
        id=uuid4(),
        lead_id=lead.id,
        requested_by=uuid4(),
        status="PENDING",
        reason="Agent reason",
    )
    db = MagicMock()
    db.execute.side_effect = [_result(lead), _result(request)]

    lead_service.review_lead_close_request(
        db,
        request=request,
        lead=lead,
        approved=approved,
        actor_user_id=actor_id,
        actor_roles=("super_admin",),
        actor_agency_id=None,
        reason="Admin reason",
    )

    assert lead.status == expected_status
    assert request.status == expected_request_status
    assert request.reviewed_by == actor_id
    assert request.review_reason == "Admin reason"
    if approved:
        assert lead.closed_at is not None
        assert lead.closed_by_admin_id == actor_id
        assert lead.close_reason == "Admin reason"
    else:
        assert lead.request_close_at is None


def test_repeated_close_review_is_rejected_without_second_transition() -> None:
    lead = _lead(status="REQUEST_FOR_CLOSE")
    request = LeadCloseRequest(
        id=uuid4(),
        lead_id=lead.id,
        requested_by=uuid4(),
        status="APPROVED",
    )
    db = MagicMock()
    db.execute.side_effect = [_result(lead), _result(request)]

    with pytest.raises(HTTPException) as exc:
        lead_service.review_lead_close_request(
            db,
            request=request,
            lead=lead,
            approved=True,
            actor_user_id=uuid4(),
            actor_roles=("super_admin",),
            actor_agency_id=None,
        )

    assert exc.value.status_code == 409
    assert lead.status == "REQUEST_FOR_CLOSE"


def test_deal_closure_cannot_bypass_lead_close_workflow() -> None:
    lead = _lead(status="IN_PROGRESS")
    db = MagicMock()
    db.execute.return_value = _result(lead)

    with pytest.raises(HTTPException) as exc:
        deal_closure_service._assert_linked_lead_closed(db, lead.id)

    assert exc.value.status_code == 409
    statement = db.execute.call_args.args[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))


def test_deal_closure_accepts_lead_closed_by_workflow() -> None:
    lead = _lead(status="CLOSED")
    db = MagicMock()
    db.execute.return_value = _result(lead)

    deal_closure_service._assert_linked_lead_closed(db, lead.id)


def test_approve_lead_close_backfills_when_request_close_at_without_pending(monkeypatch) -> None:
    actor_id = uuid4()
    agent_id = uuid4()
    lead = _lead(status="IN_PROGRESS", assigned_agent_id=agent_id)
    lead.request_close_at = lead_service.utc_now()
    backfilled = LeadCloseRequest(id=uuid4(), lead_id=lead.id, requested_by=agent_id, status="PENDING")
    backfill_called = {"value": False}

    monkeypatch.setattr(lead_service, "get_lead_for_update_or_404", lambda db, lead_id: lead)
    monkeypatch.setattr(lead_service, "assert_lead_writable", lambda db, lead: None)
    monkeypatch.setattr(lead_service, "find_pending_lead_close_request", lambda *args, **kwargs: None)

    def fake_backfill(db, *, lead, reason=None):
        backfill_called["value"] = True
        lead.status = "REQUEST_FOR_CLOSE"
        return backfilled

    monkeypatch.setattr(lead_service, "_backfill_pending_lead_close_request", fake_backfill)

    def fake_review(db, **kwargs):
        kwargs["lead"].status = "CLOSED"
        kwargs["request"].status = "APPROVED"
        return kwargs["request"]

    monkeypatch.setattr(lead_service, "review_lead_close_request", fake_review)

    result = lead_service.approve_lead_close(
        MagicMock(),
        lead=lead,
        actor_user_id=actor_id,
        actor_roles=("admin",),
        actor_agency_id=uuid4(),
    )

    assert backfill_called["value"] is True
    assert result.status == "APPROVED"
