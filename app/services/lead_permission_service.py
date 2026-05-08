"""Centralized lead access and scope checks."""

from __future__ import annotations

from app.models.property_normalized import Lead, LeadNote
from app.models.user import User
from app.repositories.lead_repository import LeadRepository
from app.utils.constants import UserRoles


class LeadPermissionService:
    """Enforces role and assignment scope rules for lead operations."""

    def __init__(self, repo: LeadRepository) -> None:
        self._repo = repo

    def ensure_user_can_access_lead(self, *, actor: User, lead: Lead) -> None:
        role = self._normalize_role(actor)
        if role == UserRoles.AGENT:
            if lead.assigned_agent_id != actor.id:
                raise PermissionError("Agent can only access assigned leads")
            return
        if role == UserRoles.REGISTERED_USER:
            if lead.user_id != actor.id:
                raise PermissionError("Registered user can only access own leads")
            return
        if role == UserRoles.ADMIN:
            return
        raise PermissionError("Unsupported role for lead access")

    def ensure_admin_can_manage_agent(self, *, admin_user: User, agent_id) -> None:
        if self._normalize_role(admin_user) != UserRoles.ADMIN:
            raise PermissionError("Only admins can perform this action")

    def ensure_can_modify_note(self, *, actor: User, lead: Lead, note: LeadNote) -> None:
        self.ensure_user_can_access_lead(actor=actor, lead=lead)
        role = self._normalize_role(actor)
        if role == UserRoles.REGISTERED_USER:
            raise PermissionError("Registered user cannot modify lead notes")
        if role == UserRoles.ADMIN:
            return
        if note.author_user_id != actor.id:
            raise PermissionError("Only note creator or admin can modify this note")

    @staticmethod
    def _normalize_role(actor: User) -> str:
        roles = {r.name for r in actor.roles}
        if UserRoles.ADMIN in roles:
            return UserRoles.ADMIN
        if UserRoles.AGENT in roles:
            return UserRoles.AGENT
        if UserRoles.REGISTERED_USER in roles:
            return UserRoles.REGISTERED_USER
        return ""
