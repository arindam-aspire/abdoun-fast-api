from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.property_normalized import Lead, LeadNote
from app.services.lead_permission_service import LeadPermissionService


def _user(role_name: str):
    u = MagicMock()
    u.id = uuid4()
    role = MagicMock()
    role.name = role_name
    u.roles = [role]
    return u


def test_agent_scope_restriction_blocks_other_agent_lead() -> None:
    repo = MagicMock()
    svc = LeadPermissionService(repo)
    actor = _user("agent")
    lead = Lead(id=uuid4(), assigned_agent_id=uuid4(), source="EMAIL_FORM", status="NEW")

    with pytest.raises(PermissionError):
        svc.ensure_user_can_access_lead(actor=actor, lead=lead)


def test_admin_has_full_access_to_lead() -> None:
    repo = MagicMock()
    svc = LeadPermissionService(repo)
    actor = _user("admin")
    lead = Lead(id=uuid4(), assigned_agent_id=uuid4(), source="EMAIL_FORM", status="NEW")

    svc.ensure_user_can_access_lead(actor=actor, lead=lead)


def test_note_ownership_for_agent_enforced() -> None:
    repo = MagicMock()
    svc = LeadPermissionService(repo)
    actor = _user("agent")
    lead = Lead(id=uuid4(), assigned_agent_id=actor.id, source="EMAIL_FORM", status="NEW")
    note = LeadNote(id=uuid4(), lead_id=lead.id, author_user_id=uuid4(), note="x")

    with pytest.raises(PermissionError):
        svc.ensure_can_modify_note(actor=actor, lead=lead, note=note)


def test_registered_user_can_access_own_lead() -> None:
    repo = MagicMock()
    svc = LeadPermissionService(repo)
    actor = _user("registered_user")
    lead = Lead(id=uuid4(), user_id=actor.id, source="EMAIL_FORM", status="NEW")

    svc.ensure_user_can_access_lead(actor=actor, lead=lead)


def test_registered_user_cannot_access_another_users_lead() -> None:
    repo = MagicMock()
    svc = LeadPermissionService(repo)
    actor = _user("registered_user")
    lead = Lead(id=uuid4(), user_id=uuid4(), source="EMAIL_FORM", status="NEW")

    with pytest.raises(PermissionError):
        svc.ensure_user_can_access_lead(actor=actor, lead=lead)


def test_registered_user_cannot_modify_note_even_on_own_lead() -> None:
    repo = MagicMock()
    svc = LeadPermissionService(repo)
    actor = _user("registered_user")
    lead = Lead(id=uuid4(), user_id=actor.id, source="EMAIL_FORM", status="IN_PROGRESS")
    note = LeadNote(id=uuid4(), lead_id=lead.id, author_user_id=actor.id, note="x")

    with pytest.raises(PermissionError):
        svc.ensure_can_modify_note(actor=actor, lead=lead, note=note)
