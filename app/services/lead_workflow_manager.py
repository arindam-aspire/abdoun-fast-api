"""Lead status transition policy manager."""

from __future__ import annotations


class LeadWorkflowManager:
    """Owns and validates lead status transitions."""

    _ALLOWED_TRANSITIONS = {
        "NEW": {"IN_PROGRESS"},
        "IN_PROGRESS": {"REQUEST_FOR_CLOSE"},
        "REQUEST_FOR_CLOSE": {"CLOSED"},
        "CLOSED": set(),
    }

    def validate_transition(self, *, from_status: str, to_status: str) -> None:
        from_key = (from_status or "").upper()
        to_key = (to_status or "").upper()
        if from_key not in self._ALLOWED_TRANSITIONS:
            raise ValueError(f"Unknown current status: {from_status}")
        if to_key not in self._ALLOWED_TRANSITIONS:
            raise ValueError(f"Unknown target status: {to_status}")
        if to_key not in self._ALLOWED_TRANSITIONS[from_key]:
            raise ValueError(f"Invalid status transition: {from_status} -> {to_status}")
