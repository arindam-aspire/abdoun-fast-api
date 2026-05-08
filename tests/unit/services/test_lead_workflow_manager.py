from __future__ import annotations

import pytest

from app.services.lead_workflow_manager import LeadWorkflowManager


def test_validate_transition_accepts_defined_flow() -> None:
    manager = LeadWorkflowManager()
    manager.validate_transition(from_status="NEW", to_status="IN_PROGRESS")
    manager.validate_transition(from_status="IN_PROGRESS", to_status="REQUEST_FOR_CLOSE")
    manager.validate_transition(from_status="REQUEST_FOR_CLOSE", to_status="CLOSED")


def test_validate_transition_rejects_invalid_transition() -> None:
    manager = LeadWorkflowManager()
    with pytest.raises(ValueError):
        manager.validate_transition(from_status="NEW", to_status="CLOSED")


def test_validate_transition_rejects_closed_terminal() -> None:
    manager = LeadWorkflowManager()
    with pytest.raises(ValueError):
        manager.validate_transition(from_status="CLOSED", to_status="IN_PROGRESS")
