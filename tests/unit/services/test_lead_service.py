from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.property_normalized import Lead
from app.services.lead_service import LeadService


def _user_with_role(role: str):
    u = MagicMock()
    u.id = uuid4()
    role_obj = MagicMock()
    role_obj.name = role
    u.roles = [role_obj]
    return u


def _build_service(repo: MagicMock, permission: MagicMock | None = None) -> LeadService:
    workflow = MagicMock()
    permission_svc = permission or MagicMock()
    audit = MagicMock()
    notifications = MagicMock()
    repo.allocate_next_lead_number.return_value = "LD-2026-000001"
    repo.get_property_summaries_by_ids.return_value = {}
    repo.get_agent_summaries_by_ids.return_value = {}
    return LeadService(
        repo=repo,
        workflow=workflow,
        permission=permission_svc,
        audit=audit,
        notifications=notifications,
    )


def test_create_contact_form_lead_returns_existing_on_dedupe() -> None:
    repo = MagicMock()
    existing = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000010",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.find_recent_duplicate_contact_form_lead.return_value = existing
    service = _build_service(repo)
    actor = _user_with_role("registered_user")

    out = service.create_contact_form_lead(actor=actor, property_id=existing.property_id, message="Need details")

    assert out["id"] == str(existing.id)
    assert out["leadNumber"] == "LD-2026-000010"
    repo.create_lead.assert_not_called()


def test_create_contact_form_lead_success_creates_and_audits() -> None:
    repo = MagicMock()
    repo.find_recent_duplicate_contact_form_lead.return_value = None
    property_id = uuid4()
    actor = _user_with_role("registered_user")
    assigned_agent_id = uuid4()
    repo.get_property_listing_agent_id.return_value = assigned_agent_id
    captured = {}

    def _capture_create(*, lead):
        captured["lead"] = lead
        return lead

    repo.create_lead.side_effect = _capture_create
    service = _build_service(repo)

    out = service.create_contact_form_lead(actor=actor, property_id=property_id, message="Need details now")

    assert out["status"] == "NEW"
    assert out["leadNumber"] == "LD-2026-000001"
    assert captured["lead"].assigned_agent_id == assigned_agent_id
    assert captured["lead"].lead_number == "LD-2026-000001"
    repo.allocate_next_lead_number.assert_called_once()
    repo.commit.assert_called_once()


def test_create_contact_form_lead_accepts_property_hash() -> None:
    repo = MagicMock()
    repo.find_recent_duplicate_contact_form_lead.return_value = None
    resolved_property_id = uuid4()
    repo.get_property_id_by_hash.return_value = resolved_property_id
    assigned_agent_id = uuid4()
    repo.get_property_listing_agent_id.return_value = assigned_agent_id
    actor = _user_with_role("registered_user")
    service = _build_service(repo)

    out = service.create_contact_form_lead(actor=actor, property_id="981376612", message="Need details now")

    assert out["propertyId"] == str(resolved_property_id)
    repo.get_property_id_by_hash.assert_called_once_with(property_hash=981376612)
    repo.get_property_listing_agent_id.assert_called_once_with(property_id=resolved_property_id)


def test_update_status_closed_forbidden_for_agent() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="REQUEST_FOR_CLOSE",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    permission = MagicMock()
    service = _build_service(repo, permission=permission)
    actor = _user_with_role("agent")

    with pytest.raises(HTTPException) as exc:
        service.update_status(actor=actor, lead_id=lead.id, to_status="CLOSED")
    assert exc.value.status_code == 403


def test_update_status_invalid_transition_returns_400() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    workflow = MagicMock()
    workflow.validate_transition.side_effect = ValueError("Invalid status transition: NEW -> CLOSED")
    permission = MagicMock()
    repo.allocate_next_lead_number = MagicMock(return_value="LD-2026-000001")
    repo.get_property_summaries_by_ids = MagicMock(return_value={})
    service = LeadService(
        repo=repo,
        workflow=workflow,
        permission=permission,
        audit=MagicMock(),
        notifications=MagicMock(),
    )
    actor = _user_with_role("agent")

    with pytest.raises(HTTPException) as exc:
        service.update_status(actor=actor, lead_id=lead.id, to_status="CLOSED")
    assert exc.value.status_code == 400
    assert "Invalid status transition" in str(exc.value.detail)


def test_update_status_writes_audit_record() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    workflow = MagicMock()
    permission = MagicMock()
    audit = MagicMock()
    notifications = MagicMock()
    repo.allocate_next_lead_number = MagicMock(return_value="LD-2026-000001")
    repo.get_property_summaries_by_ids = MagicMock(return_value={})
    service = LeadService(
        repo=repo,
        workflow=workflow,
        permission=permission,
        audit=audit,
        notifications=notifications,
    )
    actor = _user_with_role("agent")

    out = service.update_status(actor=actor, lead_id=lead.id, to_status="IN_PROGRESS")

    assert out["status"] == "IN_PROGRESS"
    audit.record_status_transition.assert_called_once()


def test_list_admin_leads_uses_full_access_query() -> None:
    repo = MagicMock()
    repo.list_admin_leads.return_value = ([], 0)
    service = _build_service(repo, permission=MagicMock())
    actor = _user_with_role("admin")

    out = service.list_admin_leads(actor=actor, status=None, source=None, page=1, page_size=20)

    assert out["total"] == 0
    repo.list_admin_leads.assert_called_once()


def test_update_status_no_notification_on_commit_failure() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    repo.commit.side_effect = RuntimeError("db error")
    repo.allocate_next_lead_number = MagicMock(return_value="LD-2026-000001")
    repo.get_property_summaries_by_ids = MagicMock(return_value={})
    notifications = MagicMock()
    service = LeadService(
        repo=repo,
        workflow=MagicMock(),
        permission=MagicMock(),
        audit=MagicMock(),
        notifications=notifications,
    )
    actor = _user_with_role("agent")

    with pytest.raises(HTTPException):
        service.update_status(actor=actor, lead_id=lead.id, to_status="IN_PROGRESS")
    notifications.emit_lead_event.assert_not_called()


def test_reply_to_lead_auto_promotes_new_to_in_progress() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    msg_row = MagicMock()
    msg_row.id = uuid4()
    msg_row.lead_id = lead.id
    msg_row.sender_user_id = lead.assigned_agent_id
    msg_row.recipient_user_id = lead.user_id
    msg_row.message = "Thanks"
    msg_row.channel = "IN_APP"
    msg_row.delivery_state = "queued"
    msg_row.created_at = datetime.now(timezone.utc)
    repo.create_message.return_value = msg_row

    service = _build_service(repo, permission=MagicMock())
    actor = _user_with_role("agent")
    actor.id = lead.assigned_agent_id

    out = service.reply_to_lead(actor=actor, lead_id=lead.id, message="Thanks")

    assert out["leadId"] == str(lead.id)
    assert lead.status == "IN_PROGRESS"


def test_admin_manual_lead_creation_calls_scope_check() -> None:
    repo = MagicMock()
    permission = MagicMock()
    service = _build_service(repo, permission=permission)
    actor = _user_with_role("admin")
    property_id = uuid4()
    agent_id = uuid4()
    captured = {}

    def _capture_create(*, lead):
        captured["lead"] = lead
        return lead

    repo.create_lead.side_effect = _capture_create
    out = service.create_admin_manual_lead(
        actor=actor,
        property_id=property_id,
        assigned_agent_id=agent_id,
        source="PHONE",
        message="Manual phone lead",
    )

    permission.ensure_admin_can_manage_agent.assert_called_once()
    assert out["source"] == "PHONE"
    assert out["leadNumber"] == "LD-2026-000001"
    assert captured["lead"].lead_number == "LD-2026-000001"


def test_reassign_lead_updates_assigned_agent() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="IN_PROGRESS",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    permission = MagicMock()
    service = _build_service(repo, permission=permission)
    actor = _user_with_role("admin")
    new_agent = uuid4()

    out = service.reassign_lead(actor=actor, lead_id=lead.id, new_agent_id=new_agent)

    assert out["assignedAgentId"] == str(new_agent)
    repo.commit.assert_called_once()


def test_close_decision_by_admin_sets_closed_fields() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="REQUEST_FOR_CLOSE",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    actor = _user_with_role("admin")

    out = service.update_status(actor=actor, lead_id=lead.id, to_status="CLOSED")

    assert out["status"] == "CLOSED"
    assert lead.closed_by_admin_id == actor.id
    repo.unpublish_property_on_lead_close.assert_called_once_with(
        property_id=lead.property_id,
        actor_user_id=actor.id,
        reason="Lead closed by admin",
    )


def test_registered_user_notes_forbidden() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="IN_PROGRESS",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    with pytest.raises(HTTPException) as exc:
        service.add_note(actor=actor, lead_id=lead.id, note="user note")
    assert exc.value.status_code == 403


def test_registered_user_history_forbidden() -> None:
    repo = MagicMock()
    service = _build_service(repo, permission=MagicMock())
    actor = _user_with_role("registered_user")

    with pytest.raises(HTTPException) as exc:
        service.list_history(actor=actor, lead_id=uuid4())
    assert exc.value.status_code == 403


def test_list_my_leads_includes_lead_number_and_property_summary() -> None:
    repo = MagicMock()
    pid = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=pid,
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000003",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.list_user_leads.return_value = ([lead], 1)
    summary = {
        pid: {
            "id": str(pid),
            "title": "Sunset Villa",
            "slug": "sunset-villa",
            "thumbnailUrl": "https://cdn.example.com/sunset-thumb.jpg",
            "propertyHash": 981376612,
        }
    }
    service = _build_service(repo, permission=MagicMock())
    repo.get_property_summaries_by_ids.return_value = summary
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    out = service.list_my_leads(actor=actor, status=None, source=None, page=1, page_size=20)

    assert out["items"][0]["leadNumber"] == "LD-2026-000003"
    assert out["items"][0]["property"]["title"] == "Sunset Villa"
    assert out["items"][0]["property"]["id"] == str(pid)
    assert out["items"][0]["property"]["thumbnailUrl"] == "https://cdn.example.com/sunset-thumb.jpg"
    assert out["items"][0]["property"]["propertyHash"] == 981376612
    repo.get_property_summaries_by_ids.assert_called_once_with([pid])


def test_get_lead_detail_includes_property_hash_in_summary() -> None:
    repo = MagicMock()
    pid = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=pid,
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000005",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    repo.get_property_summaries_by_ids.return_value = {
        pid: {
            "id": str(pid),
            "title": "Ocean View",
            "slug": "ocean-view",
            "thumbnailUrl": None,
            "propertyHash": 123456789,
        }
    }
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    out = service.get_lead_detail(actor=actor, lead_id=lead.id)

    assert out["property"]["propertyHash"] == 123456789
    assert out["property"]["thumbnailUrl"] is None
    assert out["property"]["title"] == "Ocean View"
    assert out["property"]["slug"] == "ocean-view"


def test_list_my_leads_includes_assigned_agent_summary() -> None:
    repo = MagicMock()
    pid = uuid4()
    agent_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=pid,
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=agent_id,
        message="Need details",
        lead_number="LD-2026-000006",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.list_user_leads.return_value = ([lead], 1)
    service = _build_service(repo, permission=MagicMock())
    repo.get_property_summaries_by_ids.return_value = {
        pid: {"id": str(pid), "title": "Sunset Villa", "slug": "sunset-villa", "propertyHash": 981376612}
    }
    repo.get_agent_summaries_by_ids.return_value = {
        agent_id: {
            "id": str(agent_id),
            "fullName": "John Agent",
            "email": "john@example.com",
            "phone": "+962790000001",
        }
    }
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    out = service.list_my_leads(actor=actor, status=None, source=None, page=1, page_size=20)

    assert out["items"][0]["assignedAgentId"] == str(agent_id)
    assert out["items"][0]["assignedAgent"] == {
        "id": str(agent_id),
        "fullName": "John Agent",
        "email": "john@example.com",
        "phone": "+962790000001",
    }
    assert out["items"][0]["leadNumber"] == "LD-2026-000006"
    assert out["items"][0]["property"]["propertyHash"] == 981376612
    repo.get_agent_summaries_by_ids.assert_called_once_with({agent_id})


def test_list_my_leads_includes_user_summary_with_batch_lookup() -> None:
    repo = MagicMock()
    pid = uuid4()
    user_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=pid,
        user_id=user_id,
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000006",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.list_user_leads.return_value = ([lead], 1)
    service = _build_service(repo, permission=MagicMock())
    repo.get_user_summaries_by_ids.return_value = {
        user_id: {
            "id": str(user_id),
            "fullName": "Submitted User",
            "email": "submitted@example.com",
            "phone": "+962799999999",
        }
    }
    actor = _user_with_role("registered_user")
    actor.id = user_id

    out = service.list_my_leads(actor=actor, status=None, source=None, page=1, page_size=20)

    assert out["items"][0]["userId"] == str(user_id)
    assert out["items"][0]["user"] == {
        "id": str(user_id),
        "fullName": "Submitted User",
        "email": "submitted@example.com",
        "phone": "+962799999999",
    }
    repo.get_user_summaries_by_ids.assert_called_once_with({user_id})


def test_get_lead_detail_includes_assigned_agent_summary() -> None:
    repo = MagicMock()
    pid = uuid4()
    agent_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=pid,
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=agent_id,
        message="Need details",
        lead_number="LD-2026-000007",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    repo.get_property_summaries_by_ids.return_value = {
        pid: {"id": str(pid), "title": "Ocean View", "slug": "ocean-view", "propertyHash": 123456789}
    }
    repo.get_agent_summaries_by_ids.return_value = {
        agent_id: {
            "id": str(agent_id),
            "fullName": "Jane Agent",
            "email": "jane@example.com",
            "phone": None,
        }
    }
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    out = service.get_lead_detail(actor=actor, lead_id=lead.id)

    assert out["assignedAgent"] == {
        "id": str(agent_id),
        "fullName": "Jane Agent",
        "email": "jane@example.com",
        "phone": None,
    }
    assert out["assignedAgentId"] == str(agent_id)
    assert out["property"]["title"] == "Ocean View"


def test_get_lead_detail_includes_user_summary() -> None:
    repo = MagicMock()
    pid = uuid4()
    user_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=pid,
        user_id=user_id,
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000010",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    repo.get_user_summaries_by_ids.return_value = {
        user_id: {
            "id": str(user_id),
            "fullName": "Detail User",
            "email": "detail@example.com",
            "phone": None,
        }
    }
    actor = _user_with_role("registered_user")
    actor.id = user_id

    out = service.get_lead_detail(actor=actor, lead_id=lead.id)

    assert out["userId"] == str(user_id)
    assert out["user"] == {
        "id": str(user_id),
        "fullName": "Detail User",
        "email": "detail@example.com",
        "phone": None,
    }


def test_assigned_agent_summary_null_when_no_assigned_agent_id() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=None,
        message="Need details",
        lead_number="LD-2026-000008",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    out = service.get_lead_detail(actor=actor, lead_id=lead.id)

    assert out["assignedAgentId"] is None
    assert out["assignedAgent"] is None
    repo.get_agent_summaries_by_ids.assert_not_called()


def test_user_summary_null_when_user_missing_but_user_id_remains() -> None:
    repo = MagicMock()
    user_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=user_id,
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000011",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    repo.get_user_summaries_by_ids.return_value = {}
    actor = _user_with_role("registered_user")
    actor.id = user_id

    out = service.get_lead_detail(actor=actor, lead_id=lead.id)

    assert out["userId"] == str(user_id)
    assert out["user"] is None


def test_assigned_agent_summary_null_when_agent_user_missing() -> None:
    repo = MagicMock()
    agent_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="NEW",
        assigned_agent_id=agent_id,
        message="Need details",
        lead_number="LD-2026-000009",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    repo.get_agent_summaries_by_ids.return_value = {}
    actor = _user_with_role("registered_user")
    actor.id = lead.user_id

    out = service.get_lead_detail(actor=actor, lead_id=lead.id)

    assert out["assignedAgentId"] == str(agent_id)
    assert out["assignedAgent"] is None


def test_reassign_creates_history_audit_entry() -> None:
    repo = MagicMock()
    old_agent_id = uuid4()
    new_agent_id = uuid4()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="IN_PROGRESS",
        assigned_agent_id=old_agent_id,
        message="Need details",
        lead_number="LD-2026-000012",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    audit = MagicMock()
    service = LeadService(
        repo=repo,
        workflow=MagicMock(),
        permission=MagicMock(),
        audit=audit,
        notifications=MagicMock(),
    )
    repo.get_property_summaries_by_ids.return_value = {}
    repo.get_agent_summaries_by_ids.return_value = {}
    repo.get_user_summaries_by_ids.return_value = {}
    actor = _user_with_role("admin")

    service.reassign_lead(actor=actor, lead_id=lead.id, new_agent_id=new_agent_id)

    audit.record_status_transition.assert_called_once()
    kwargs = audit.record_status_transition.call_args.kwargs
    assert kwargs["from_status"] == "IN_PROGRESS"
    assert kwargs["to_status"] == "IN_PROGRESS"
    assert kwargs["actor_role"] == "admin"
    assert str(old_agent_id) in kwargs["reason"]
    assert str(new_agent_id) in kwargs["reason"]


def test_close_decision_records_closed_history_entry() -> None:
    repo = MagicMock()
    lead = Lead(
        id=uuid4(),
        property_id=uuid4(),
        user_id=uuid4(),
        source="EMAIL_FORM",
        status="REQUEST_FOR_CLOSE",
        assigned_agent_id=uuid4(),
        message="Need details",
        lead_number="LD-2026-000013",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    audit = MagicMock()
    service = LeadService(
        repo=repo,
        workflow=MagicMock(),
        permission=MagicMock(),
        audit=audit,
        notifications=MagicMock(),
    )
    repo.get_property_summaries_by_ids.return_value = {}
    repo.get_agent_summaries_by_ids.return_value = {}
    repo.get_user_summaries_by_ids.return_value = {}
    actor = _user_with_role("admin")

    service.update_status(actor=actor, lead_id=lead.id, to_status="CLOSED", reason="approved")

    audit.record_status_transition.assert_called_once()
    kwargs = audit.record_status_transition.call_args.kwargs
    assert kwargs["from_status"] == "REQUEST_FOR_CLOSE"
    assert kwargs["to_status"] == "CLOSED"
    assert kwargs["actor_role"] == "admin"
    assert kwargs["reason"] == "approved"


def test_successive_creates_use_distinct_allocated_lead_numbers() -> None:
    repo = MagicMock()
    repo.find_recent_duplicate_contact_form_lead.return_value = None
    prop = uuid4()
    repo.get_property_listing_agent_id.return_value = uuid4()
    repo.create_lead.side_effect = lambda *, lead: lead
    service = _build_service(repo)
    repo.allocate_next_lead_number.side_effect = ["LD-2026-000001", "LD-2026-000002"]

    service.create_contact_form_lead(actor=_user_with_role("registered_user"), property_id=prop, message="first message here")
    service.create_contact_form_lead(actor=_user_with_role("registered_user"), property_id=prop, message="second message here ok")

    assert repo.allocate_next_lead_number.call_count == 2


def test_agent_can_create_manual_owner_lead() -> None:
    repo = MagicMock()
    captured = {}

    def _capture_create(*, lead):
        captured["lead"] = lead
        return lead

    repo.create_lead.side_effect = _capture_create
    audit = MagicMock()
    service = LeadService(
        repo=repo,
        workflow=MagicMock(),
        permission=MagicMock(),
        audit=audit,
        notifications=MagicMock(),
    )
    repo.allocate_next_lead_number.return_value = "LD-2026-000014"
    repo.get_agent_summaries_by_ids.return_value = {}
    actor = _user_with_role("agent")

    out = service.create_manual_owner_lead(
        actor=actor,
        owner_name="Owner Name",
        phone_number="+962799999999",
        email="owner@example.com",
        message="Owner wants to sell property",
        related_property_name="Villa in Abdoun",
    )

    lead = captured["lead"]
    assert out["leadNumber"] == "LD-2026-000014"
    assert out["status"] == "NEW"
    assert out["source"] == "AGENT_MANUAL"
    assert out["communicationMode"] == "EXTERNAL"
    assert out["assignedAgentId"] == str(actor.id)
    assert out["userId"] is None
    assert out["propertyId"] is None
    assert out["externalOwner"] == {
        "name": "Owner Name",
        "email": "owner@example.com",
        "phone": "+962799999999",
    }
    assert out["externalPropertyName"] == "Villa in Abdoun"
    assert lead.assigned_agent_id == actor.id
    assert lead.created_by_agent_id == actor.id
    audit.record_status_transition.assert_called_once()
    assert audit.record_status_transition.call_args.kwargs["reason"] == "Manual owner lead created"


def test_registered_user_cannot_create_manual_owner_lead() -> None:
    service = _build_service(MagicMock())
    actor = _user_with_role("registered_user")

    with pytest.raises(HTTPException) as exc:
        service.create_manual_owner_lead(
            actor=actor,
            owner_name="Owner Name",
            phone_number="+962799999999",
            email=None,
            message="Owner wants to sell property",
            related_property_name="Villa in Abdoun",
        )

    assert exc.value.status_code == 403


def test_manual_owner_lead_appears_in_agent_list_payload() -> None:
    repo = MagicMock()
    actor = _user_with_role("agent")
    lead = Lead(
        id=uuid4(),
        property_id=None,
        user_id=None,
        source="AGENT_MANUAL",
        status="NEW",
        assigned_agent_id=actor.id,
        message="Owner wants to sell property",
        lead_number="LD-2026-000015",
        external_owner_name="Owner Name",
        external_owner_email="owner@example.com",
        external_owner_phone="+962799999999",
        external_property_name="Villa in Abdoun",
        communication_mode="EXTERNAL",
        created_by_agent_id=actor.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.list_agent_leads.return_value = ([lead], 1)
    service = _build_service(repo)

    out = service.list_agent_leads(actor=actor, status=None, source=None, page=1, page_size=20)

    item = out["items"][0]
    assert item["leadNumber"] == "LD-2026-000015"
    assert item["source"] == "AGENT_MANUAL"
    assert item["communicationMode"] == "EXTERNAL"
    assert item["externalOwner"]["name"] == "Owner Name"
    assert item["externalPropertyName"] == "Villa in Abdoun"
    assert item["property"] is None
    assert item["user"] is None


def test_agent_can_move_manual_lead_to_in_progress_and_request_close() -> None:
    repo = MagicMock()
    actor = _user_with_role("agent")
    lead = Lead(
        id=uuid4(),
        property_id=None,
        user_id=None,
        source="AGENT_MANUAL",
        status="NEW",
        assigned_agent_id=actor.id,
        message="Owner wants to sell property",
        lead_number="LD-2026-000016",
        communication_mode="EXTERNAL",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())
    service.update_status(actor=actor, lead_id=lead.id, to_status="IN_PROGRESS")
    assert lead.status == "IN_PROGRESS"

    service.update_status(actor=actor, lead_id=lead.id, to_status="REQUEST_FOR_CLOSE")
    assert lead.status == "REQUEST_FOR_CLOSE"


def test_admin_can_close_manual_owner_lead() -> None:
    repo = MagicMock()
    actor = _user_with_role("admin")
    lead = Lead(
        id=uuid4(),
        property_id=None,
        user_id=None,
        source="AGENT_MANUAL",
        status="REQUEST_FOR_CLOSE",
        assigned_agent_id=uuid4(),
        message="Owner wants to sell property",
        lead_number="LD-2026-000017",
        communication_mode="EXTERNAL",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())

    out = service.update_status(actor=actor, lead_id=lead.id, to_status="CLOSED", reason="approved")

    assert out["status"] == "CLOSED"
    assert lead.closed_by_admin_id == actor.id


def test_post_message_on_external_lead_returns_400() -> None:
    repo = MagicMock()
    actor = _user_with_role("agent")
    lead = Lead(
        id=uuid4(),
        property_id=None,
        user_id=None,
        source="AGENT_MANUAL",
        status="NEW",
        assigned_agent_id=actor.id,
        message="Owner wants to sell property",
        lead_number="LD-2026-000018",
        communication_mode="EXTERNAL",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())

    with pytest.raises(HTTPException) as exc:
        service.post_message(actor=actor, lead_id=lead.id, message="hello")

    assert exc.value.status_code == 400
    assert exc.value.detail == "This lead uses external communication."
    repo.create_message.assert_not_called()


def test_list_messages_on_external_lead_returns_empty_list() -> None:
    repo = MagicMock()
    actor = _user_with_role("agent")
    lead = Lead(
        id=uuid4(),
        property_id=None,
        user_id=None,
        source="AGENT_MANUAL",
        status="NEW",
        assigned_agent_id=actor.id,
        message="Owner wants to sell property",
        lead_number="LD-2026-000019",
        communication_mode="EXTERNAL",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_lead_by_id.return_value = lead
    service = _build_service(repo, permission=MagicMock())

    assert service.list_messages(actor=actor, lead_id=lead.id) == []
    repo.list_messages.assert_not_called()
