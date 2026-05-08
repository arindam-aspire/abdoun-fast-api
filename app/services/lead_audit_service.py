"""Lead audit/history persistence service."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.repositories.lead_repository import LeadRepository


class LeadAuditService:
    """Writes lead lifecycle history in one centralized path."""

    def __init__(self, repo: LeadRepository) -> None:
        self._repo = repo

    def record_status_transition(
        self,
        *,
        lead_id: UUID,
        from_status: Optional[str],
        to_status: str,
        actor_user_id: Optional[UUID],
        actor_role: Optional[str],
        reason: Optional[str] = None,
    ) -> None:
        self._repo.add_status_history(
            lead_id=lead_id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )
