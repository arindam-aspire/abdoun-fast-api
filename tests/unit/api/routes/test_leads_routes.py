from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.deps.leads import get_lead_service
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


def _fake_lead_payload():
    now = datetime.now(timezone.utc)
    pid = uuid4()
    agent_id = uuid4()
    user_id = uuid4()
    return {
        "id": uuid4(),
        "leadNumber": "LD-2026-000001",
        "propertyId": pid,
        "property": {
            "id": str(pid),
            "title": "Test Property",
            "slug": "test-property",
            "thumbnailUrl": "https://cdn.example.com/test-thumb.jpg",
            "propertyHash": 981376612,
        },
        "userId": user_id,
        "user": {
            "id": str(user_id),
            "fullName": "Test User",
            "email": "user@example.com",
            "phone": "+962799999999",
        },
        "status": "NEW",
        "source": "EMAIL_FORM",
        "assignedAgentId": agent_id,
        "assignedAgent": {
            "id": str(agent_id),
            "fullName": "Test Agent",
            "email": "agent@example.com",
            "phone": "+962790000002",
        },
        "assignedByAdminId": None,
        "message": "hello from tests",
        "lastActivityAt": now,
        "requestCloseAt": None,
        "closedAt": None,
        "closedByAdminId": None,
        "createdAt": now,
        "updatedAt": now,
    }


def _fake_offline_lead_payload():
    now = datetime.now(timezone.utc)
    agent_id = uuid4()
    return {
        "id": uuid4(),
        "leadNumber": "LD-2026-000014",
        "propertyId": None,
        "property": None,
        "userId": None,
        "user": None,
        "communicationMode": "EXTERNAL",
        "externalOwner": {
            "name": "Customer Name",
            "email": None,
            "phone": "+962799999999",
        },
        "externalPropertyName": "Villa in Abdoun",
        "createdByAgentId": agent_id,
        "createdByAdminId": None,
        "offlineLead": {
            "customerName": "Customer Name",
            "phoneNumber": "+962799999999",
            "propertyName": "Villa in Abdoun",
            "propertyId": None,
            "inquiryType": "BUY",
            "source": "PHONE",
            "notes": "Customer wants to buy",
            "createdByAgentId": str(agent_id),
            "createdByAdminId": None,
        },
        "status": "NEW",
        "source": "OFFLINE_MANUAL",
        "assignedAgentId": agent_id,
        "assignedAgent": {
            "id": str(agent_id),
            "fullName": "Test Agent",
            "email": "agent@example.com",
            "phone": "+962790000002",
        },
        "assignedByAdminId": None,
        "message": "Customer wants to buy",
        "lastActivityAt": now,
        "requestCloseAt": None,
        "closedAt": None,
        "closedByAdminId": None,
        "createdAt": now,
        "updatedAt": now,
    }


def _fake_summary():
    return {
        "total": 14,
        "NEW": 7,
        "IN_PROGRESS": 3,
        "REQUEST_FOR_CLOSE": 2,
        "CLOSED": 2,
    }


def _fake_db():
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []
    db.execute.return_value = exec_result
    try:
        yield db
    finally:
        pass


def test_contact_form_route_success() -> None:
    service = MagicMock()
    service.create_contact_form_lead.return_value = _fake_lead_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {
        "propertyId": str(uuid4()),
        "name": "John Doe",
        "email": "john@example.com",
        "phoneNumber": "+12025551234",
        "message": "I am interested in this property.",
    }
    res = client.post("/api/v1/leads/contact-form", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_contact_form_route_accepts_property_hash() -> None:
    service = MagicMock()
    service.create_contact_form_lead.return_value = _fake_lead_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {
        "propertyId": "981376612",
        "name": "Kinshuk Roy",
        "email": "k_abdoun@yopmail.com",
        "phoneNumber": "+96289654125",
        "message": "I would like to inquire about your property jk - #981376612. Please contact me at your earliest convenience.",
    }
    res = client.post("/api/v1/leads/contact-form", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_agent_list_route_success() -> None:
    service = MagicMock()
    service.list_agent_leads.return_value = {
        "items": [_fake_lead_payload()],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "summary": _fake_summary(),
    }
    app.dependency_overrides[get_current_user] = lambda: _user("agent")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/agent/leads")
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["data"]["summary"]["total"] == 14
    assert res.json()["data"]["items"][0]["property"]["thumbnailUrl"] == "https://cdn.example.com/test-thumb.jpg"
    assert res.json()["data"]["items"][0]["assignedAgent"]["phone"] == "+962790000002"
    app.dependency_overrides.clear()


def test_registered_user_my_leads_route_success() -> None:
    service = MagicMock()
    service.list_my_leads.return_value = {
        "items": [_fake_lead_payload()],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "summary": _fake_summary(),
    }
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/leads/my")
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["data"]["summary"]["NEW"] == 7
    app.dependency_overrides.clear()


def test_admin_list_route_includes_summary() -> None:
    service = MagicMock()
    service.list_admin_leads.return_value = {
        "items": [_fake_lead_payload()],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "summary": _fake_summary(),
    }
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get("/api/v1/admin/leads?status=NEW")
    assert res.status_code == 200
    assert res.json()["data"]["summary"] == _fake_summary()
    service.list_admin_leads.assert_called_once()
    app.dependency_overrides.clear()


def test_agent_offline_lead_route_success() -> None:
    service = MagicMock()
    service.create_offline_lead.return_value = _fake_offline_lead_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("agent")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {
        "customerName": "Customer Name",
        "phoneNumber": "+962799999999",
        "propertyName": "Villa in Abdoun",
        "inquiryType": "BUY",
        "source": "PHONE",
        "notes": "Customer wants to buy",
    }
    res = client.post("/api/v1/leads/manual", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["source"] == "OFFLINE_MANUAL"
    assert data["communicationMode"] == "EXTERNAL"
    assert data["externalOwner"]["name"] == "Customer Name"
    assert data["externalPropertyName"] == "Villa in Abdoun"
    assert data["offlineLead"]["source"] == "PHONE"
    service.create_offline_lead.assert_called_once()
    app.dependency_overrides.clear()


def test_admin_offline_lead_route_success() -> None:
    service = MagicMock()
    payload_data = _fake_offline_lead_payload()
    admin_id = uuid4()
    payload_data["createdByAgentId"] = None
    payload_data["createdByAdminId"] = admin_id
    payload_data["offlineLead"]["createdByAgentId"] = None
    payload_data["offlineLead"]["createdByAdminId"] = str(admin_id)
    service.create_offline_lead.return_value = payload_data
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)
    assigned_agent_id = uuid4()

    payload = {
        "customerName": "Customer Name",
        "phoneNumber": "+962799999999",
        "propertyName": "Villa in Abdoun",
        "inquiryType": "BUY",
        "source": "PHONE",
        "assignedAgentId": str(assigned_agent_id),
    }
    res = client.post("/api/v1/leads/manual", json=payload)
    assert res.status_code == 200
    assert res.json()["message"] == "Offline lead created"
    service.create_offline_lead.assert_called_once()
    app.dependency_overrides.clear()


def test_offline_lead_route_forbidden_for_registered_user() -> None:
    service = MagicMock()
    service.create_offline_lead.side_effect = HTTPException(status_code=403, detail="Unauthorized")
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {
        "customerName": "Customer Name",
        "phoneNumber": "+962799999999",
        "propertyName": "Villa in Abdoun",
        "inquiryType": "BUY",
        "source": "PHONE",
    }
    res = client.post("/api/v1/leads/manual", json=payload)
    assert res.status_code == 403
    app.dependency_overrides.clear()


def test_offline_lead_route_invalid_phone_returns_422() -> None:
    service = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: _user("agent")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {
        "customerName": "Customer Name",
        "phoneNumber": "12",
        "propertyName": "Villa in Abdoun",
        "inquiryType": "BUY",
        "source": "PHONE",
    }
    res = client.post("/api/v1/leads/manual", json=payload)
    assert res.status_code == 422
    service.create_offline_lead.assert_not_called()
    app.dependency_overrides.clear()


def test_shared_lead_detail_route_success() -> None:
    service = MagicMock()
    service.get_lead_detail.return_value = _fake_lead_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get(f"/api/v1/leads/{uuid4()}")
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_shared_messages_list_route_success() -> None:
    service = MagicMock()
    service.list_messages.return_value = [_fake_message_payload()]
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get(f"/api/v1/leads/{uuid4()}/messages")
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_shared_messages_post_route_success() -> None:
    service = MagicMock()
    service.post_message.return_value = _fake_message_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("registered_user")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.post(f"/api/v1/leads/{uuid4()}/messages", json={"message": "hello"})
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_shared_notes_list_route_success() -> None:
    service = MagicMock()
    service.list_notes.return_value = [_fake_note_payload()]
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get(f"/api/v1/leads/{uuid4()}/notes")
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_shared_notes_post_route_success() -> None:
    service = MagicMock()
    service.add_note.return_value = _fake_note_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("agent")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.post(f"/api/v1/leads/{uuid4()}/notes", json={"note": "internal"})
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_shared_history_route_success() -> None:
    service = MagicMock()
    service.list_history.return_value = [_fake_history_payload()]
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.get(f"/api/v1/leads/{uuid4()}/history")
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_admin_create_manual_lead_success() -> None:
    service = MagicMock()
    row = _fake_lead_payload()
    row["source"] = "PHONE"
    service.create_admin_manual_lead.return_value = row
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {
        "propertyId": str(uuid4()),
        "assignedAgentId": str(uuid4()),
        "source": "PHONE",
        "message": "Called and asked for details.",
    }
    res = client.post("/api/v1/admin/leads", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_admin_reassign_lead_route_success() -> None:
    service = MagicMock()
    service.reassign_lead.return_value = _fake_lead_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {"assignedAgentId": str(uuid4())}
    res = client.patch(f"/api/v1/admin/leads/{uuid4()}/reassign", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_admin_close_decision_route_success() -> None:
    service = MagicMock()
    row = _fake_lead_payload()
    row["status"] = "CLOSED"
    service.update_status.return_value = row
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    payload = {"status": "CLOSED", "reason": "approved"}
    res = client.post(f"/api/v1/admin/leads/{uuid4()}/close-decision", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
    app.dependency_overrides.clear()


def test_agent_reply_wrapper_delegates_to_post_message() -> None:
    service = MagicMock()
    service.post_message.return_value = _fake_message_payload()
    app.dependency_overrides[get_current_user] = lambda: _user("agent")
    app.dependency_overrides[get_lead_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.post(f"/api/v1/agent/leads/{uuid4()}/reply", json={"message": "agent reply"})
    assert res.status_code == 200
    service.post_message.assert_called_once()
    service.reply_to_lead.assert_not_called()
    app.dependency_overrides.clear()


def _fake_message_payload():
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "leadId": uuid4(),
        "senderUserId": uuid4(),
        "recipientUserId": uuid4(),
        "message": "hello",
        "channel": "IN_APP",
        "deliveryState": "queued",
        "createdAt": now,
    }


def _fake_note_payload():
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "leadId": uuid4(),
        "authorUserId": uuid4(),
        "note": "internal",
        "createdAt": now,
        "updatedAt": now,
    }


def _fake_history_payload():
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "leadId": uuid4(),
        "fromStatus": "NEW",
        "toStatus": "IN_PROGRESS",
        "actorUserId": uuid4(),
        "actorRole": "agent",
        "reason": "Auto-promoted after reply",
        "changedAt": now,
    }
