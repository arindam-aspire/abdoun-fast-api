"""Lead orchestration service with delegated workflow/permission/audit/notification responsibilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.property_normalized import Lead
from app.models.user import User
from app.repositories.lead_repository import LeadRepository
from app.services.lead_audit_service import LeadAuditService
from app.services.lead_notification_service import LeadNotificationService
from app.services.lead_permission_service import LeadPermissionService
from app.services.lead_workflow_manager import LeadWorkflowManager
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.status_codes import HTTPStatus


class LeadService:
    """Public entry point for lead use-cases; delegates policy concerns to focused collaborators."""

    def __init__(
        self,
        repo: LeadRepository,
        workflow: LeadWorkflowManager,
        permission: LeadPermissionService,
        audit: LeadAuditService,
        notifications: LeadNotificationService,
    ) -> None:
        self._repo = repo
        self._workflow = workflow
        self._permission = permission
        self._audit = audit
        self._notifications = notifications

    def create_contact_form_lead(
        self,
        *,
        actor: User,
        property_id: str,
        message: str,
    ) -> dict[str, Any]:
        if self._role(actor) != UserRoles.REGISTERED_USER:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)

        resolved_property_id = self._resolve_property_id(property_id)

        existing = self._repo.find_recent_duplicate_contact_form_lead(
            property_id=resolved_property_id,
            user_id=actor.id,
            message=message.strip(),
        )
        if existing:
            return self._serialize_lead(
                existing,
                property_summary=self._property_summary_for_lead(existing),
            )

        assigned_agent_id = self._repo.get_property_listing_agent_id(property_id=resolved_property_id)
        if not assigned_agent_id:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.PROPERTY_NOT_FOUND)

        now = datetime.now(timezone.utc)
        lead_number = self._repo.allocate_next_lead_number()
        lead = Lead(
            property_id=resolved_property_id,
            user_id=actor.id,
            inquiry_type="EMAIL_FORM",
            source="EMAIL_FORM",
            status="NEW",
            assigned_agent_id=assigned_agent_id,
            message=message.strip(),
            last_activity_at=now,
            lead_number=lead_number,
        )
        try:
            self._repo.create_lead(lead=lead)
            self._audit.record_status_transition(
                lead_id=lead.id,
                from_status=None,
                to_status="NEW",
                actor_user_id=actor.id,
                actor_role=UserRoles.REGISTERED_USER,
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INTERNAL_SERVER_ERROR,
            ) from exc
        self._notifications.emit_lead_event(
            event_type="lead_created",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message="Contact form lead created",
        )
        self._notifications.emit_email_hook_todo(
            event_type="lead_created",
            lead_id=str(lead.id),
            recipient_hint=str(assigned_agent_id),
        )
        return self._serialize_lead(
            lead,
            property_summary=self._property_summary_for_lead(lead),
            assigned_agent_summary=self._agent_summary_for_lead(lead),
            user_summary=self._user_summary_for_lead(lead),
        )

    def create_admin_manual_lead(
        self,
        *,
        actor: User,
        property_id: UUID,
        assigned_agent_id: UUID,
        source: str,
        message: str,
        contact_user_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        self._permission.ensure_admin_can_manage_agent(admin_user=actor, agent_id=assigned_agent_id)
        now = datetime.now(timezone.utc)
        lead_number = self._repo.allocate_next_lead_number()
        lead = Lead(
            property_id=property_id,
            user_id=contact_user_id,
            inquiry_type=source,
            source=source,
            status="NEW",
            assigned_agent_id=assigned_agent_id,
            assigned_by_admin_id=actor.id,
            message=message.strip(),
            last_activity_at=now,
            lead_number=lead_number,
        )
        try:
            self._repo.create_lead(lead=lead)
            self._audit.record_status_transition(
                lead_id=lead.id,
                from_status=None,
                to_status="NEW",
                actor_user_id=actor.id,
                actor_role=UserRoles.ADMIN,
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        self._notifications.emit_lead_event(
            event_type="admin_manual_lead_created",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message=f"Manual lead created from source {source}",
        )
        return self._serialize_lead(
            lead,
            property_summary=self._property_summary_for_lead(lead),
            assigned_agent_summary=self._agent_summary_for_lead(lead),
            user_summary=self._user_summary_for_lead(lead),
        )

    def create_manual_owner_lead(
        self,
        *,
        actor: User,
        owner_name: str,
        phone_number: Optional[str],
        email: Optional[str],
        message: str,
        related_property_name: str,
    ) -> dict[str, Any]:
        if self._role(actor) != UserRoles.AGENT:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)

        now = datetime.now(timezone.utc)
        lead_number = self._repo.allocate_next_lead_number()
        lead = Lead(
            property_id=None,
            user_id=None,
            inquiry_type="AGENT_MANUAL",
            source="AGENT_MANUAL",
            status="NEW",
            assigned_agent_id=actor.id,
            message=message.strip(),
            last_activity_at=now,
            lead_number=lead_number,
            external_owner_name=owner_name.strip(),
            external_owner_phone=phone_number.strip() if phone_number else None,
            external_owner_email=email.strip() if email else None,
            external_property_name=related_property_name.strip(),
            communication_mode="EXTERNAL",
            created_by_agent_id=actor.id,
        )
        try:
            self._repo.create_lead(lead=lead)
            self._audit.record_status_transition(
                lead_id=lead.id,
                from_status=None,
                to_status="NEW",
                actor_user_id=actor.id,
                actor_role=UserRoles.AGENT,
                reason="Manual owner lead created",
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        self._notifications.emit_lead_event(
            event_type="manual_owner_lead_created",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message="Manual owner lead created",
        )
        return self._serialize_lead(
            lead,
            assigned_agent_summary=self._agent_summary_for_lead(lead),
        )

    def list_agent_leads(
        self,
        *,
        actor: User,
        status: Optional[str],
        source: Optional[str],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        if self._role(actor) != UserRoles.AGENT:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)
        offset = (max(page, 1) - 1) * max(page_size, 1)
        rows, total = self._repo.list_agent_leads(
            agent_id=actor.id,
            status=status,
            source=source,
            limit=page_size,
            offset=offset,
        )
        property_ids = [r.property_id for r in rows if r.property_id]
        assigned_agent_ids = {r.assigned_agent_id for r in rows if r.assigned_agent_id}
        user_ids = {r.user_id for r in rows if r.user_id}
        summaries = self._repo.get_property_summaries_by_ids(property_ids) if property_ids else {}
        agent_summaries = self._repo.get_agent_summaries_by_ids(assigned_agent_ids) if assigned_agent_ids else {}
        user_summaries = self._repo.get_user_summaries_by_ids(user_ids) if user_ids else {}
        return {
            "items": [
                self._serialize_lead(
                    r,
                    property_summary=summaries.get(r.property_id),
                    assigned_agent_summary=agent_summaries.get(r.assigned_agent_id),
                    user_summary=user_summaries.get(r.user_id),
                )
                for r in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def list_admin_leads(
        self,
        *,
        actor: User,
        status: Optional[str],
        source: Optional[str],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        if self._role(actor) != UserRoles.ADMIN:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)
        offset = (max(page, 1) - 1) * max(page_size, 1)
        rows, total = self._repo.list_admin_leads(
            status=status,
            source=source,
            limit=page_size,
            offset=offset,
        )
        property_ids = [r.property_id for r in rows if r.property_id]
        assigned_agent_ids = {r.assigned_agent_id for r in rows if r.assigned_agent_id}
        user_ids = {r.user_id for r in rows if r.user_id}
        summaries = self._repo.get_property_summaries_by_ids(property_ids) if property_ids else {}
        agent_summaries = self._repo.get_agent_summaries_by_ids(assigned_agent_ids) if assigned_agent_ids else {}
        user_summaries = self._repo.get_user_summaries_by_ids(user_ids) if user_ids else {}
        return {
            "items": [
                self._serialize_lead(
                    r,
                    property_summary=summaries.get(r.property_id),
                    assigned_agent_summary=agent_summaries.get(r.assigned_agent_id),
                    user_summary=user_summaries.get(r.user_id),
                )
                for r in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def list_my_leads(
        self,
        *,
        actor: User,
        status: Optional[str],
        source: Optional[str],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        if self._role(actor) != UserRoles.REGISTERED_USER:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)
        offset = (max(page, 1) - 1) * max(page_size, 1)
        rows, total = self._repo.list_user_leads(
            user_id=actor.id,
            status=status,
            source=source,
            limit=page_size,
            offset=offset,
        )
        property_ids = [r.property_id for r in rows if r.property_id]
        assigned_agent_ids = {r.assigned_agent_id for r in rows if r.assigned_agent_id}
        user_ids = {r.user_id for r in rows if r.user_id}
        summaries = self._repo.get_property_summaries_by_ids(property_ids) if property_ids else {}
        agent_summaries = self._repo.get_agent_summaries_by_ids(assigned_agent_ids) if assigned_agent_ids else {}
        user_summaries = self._repo.get_user_summaries_by_ids(user_ids) if user_ids else {}
        return {
            "items": [
                self._serialize_lead(
                    r,
                    property_summary=summaries.get(r.property_id),
                    assigned_agent_summary=agent_summaries.get(r.assigned_agent_id),
                    user_summary=user_summaries.get(r.user_id),
                )
                for r in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_lead_detail(self, *, actor: User, lead_id: UUID) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_access(actor=actor, lead=lead)
        return self._serialize_lead(
            lead,
            property_summary=self._property_summary_for_lead(lead),
            assigned_agent_summary=self._agent_summary_for_lead(lead),
            user_summary=self._user_summary_for_lead(lead),
        )

    def update_status(
        self,
        *,
        actor: User,
        lead_id: UUID,
        to_status: str,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_access(actor=actor, lead=lead)
        try:
            self._workflow.validate_transition(from_status=str(lead.status), to_status=to_status)
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        role = self._role(actor)
        if to_status == "CLOSED" and role != UserRoles.ADMIN:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)

        previous_status = str(lead.status)
        now = datetime.now(timezone.utc)
        lead.status = to_status
        lead.last_activity_at = now
        if to_status == "REQUEST_FOR_CLOSE":
            lead.request_close_at = now
        if to_status == "CLOSED":
            lead.closed_at = now
            lead.closed_by_admin_id = actor.id
            if lead.property_id:
                self._repo.unpublish_property_on_lead_close(
                    property_id=lead.property_id,
                    actor_user_id=actor.id,
                    reason="Lead closed by admin",
                )
        try:
            self._audit.record_status_transition(
                lead_id=lead.id,
                from_status=previous_status,
                to_status=to_status,
                actor_user_id=actor.id,
                actor_role=role,
                reason=reason,
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc

        self._notifications.emit_lead_event(
            event_type="lead_status_changed",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message=f"{previous_status} -> {to_status}",
        )
        self._notifications.emit_email_hook_todo(
            event_type="lead_status_changed",
            lead_id=str(lead.id),
        )
        return self._serialize_lead(lead, property_summary=self._property_summary_for_lead(lead))

    def reassign_lead(self, *, actor: User, lead_id: UUID, new_agent_id: UUID) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        if self._role(actor) != UserRoles.ADMIN:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)
        self._permission.ensure_admin_can_manage_agent(admin_user=actor, agent_id=new_agent_id)
        self._ensure_access(actor=actor, lead=lead)
        old_agent_id = lead.assigned_agent_id
        lead.assigned_agent_id = new_agent_id
        lead.assigned_by_admin_id = actor.id
        lead.last_activity_at = datetime.now(timezone.utc)
        try:
            self._audit.record_status_transition(
                lead_id=lead.id,
                from_status=str(lead.status),
                to_status=str(lead.status),
                actor_user_id=actor.id,
                actor_role=UserRoles.ADMIN,
                reason=f"Reassigned agent from {old_agent_id or 'unassigned'} to {new_agent_id}",
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        self._notifications.emit_lead_event(
            event_type="lead_reassigned",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message=f"Lead reassigned to {new_agent_id}",
        )
        return self._serialize_lead(lead, property_summary=self._property_summary_for_lead(lead))

    def add_note(self, *, actor: User, lead_id: UUID, note: str) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_notes_access_allowed(actor=actor)
        self._ensure_access(actor=actor, lead=lead)
        try:
            row = self._repo.create_note(lead_id=lead.id, author_user_id=actor.id, note=note.strip())
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        self._notifications.emit_lead_event(
            event_type="lead_note_added",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
        )
        return self._serialize_note(row)

    def list_notes(self, *, actor: User, lead_id: UUID) -> list[dict[str, Any]]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_notes_access_allowed(actor=actor)
        self._ensure_access(actor=actor, lead=lead)
        rows = self._repo.list_notes(lead_id=lead.id)
        return [self._serialize_note(row) for row in rows]

    def update_note(self, *, actor: User, lead_id: UUID, note_id: UUID, note: str) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_notes_access_allowed(actor=actor)
        note_row = self._repo.get_note(note_id=note_id)
        if not note_row or note_row.lead_id != lead.id:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.NOT_FOUND)
        self._permission.ensure_can_modify_note(actor=actor, lead=lead, note=note_row)
        note_row.note = note.strip()
        note_row.updated_at = datetime.now(timezone.utc)
        try:
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        return self._serialize_note(note_row)

    def delete_note(self, *, actor: User, lead_id: UUID, note_id: UUID) -> bool:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_notes_access_allowed(actor=actor)
        note_row = self._repo.get_note(note_id=note_id)
        if not note_row or note_row.lead_id != lead.id:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.NOT_FOUND)
        self._permission.ensure_can_modify_note(actor=actor, lead=lead, note=note_row)
        try:
            self._repo.delete_note(note=note_row)
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        return True

    def reply_to_lead(self, *, actor: User, lead_id: UUID, message: str) -> dict[str, Any]:
        return self.post_message(actor=actor, lead_id=lead_id, message=message)

    def list_messages(self, *, actor: User, lead_id: UUID) -> list[dict[str, Any]]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_access(actor=actor, lead=lead)
        if self._communication_mode(lead) == "EXTERNAL":
            return []
        rows = self._repo.list_messages(lead_id=lead.id)
        return [self._serialize_message(row) for row in rows]

    def post_message(self, *, actor: User, lead_id: UUID, message: str) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_access(actor=actor, lead=lead)
        if self._communication_mode(lead) == "EXTERNAL":
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="This lead uses external communication.")
        try:
            row = self._repo.create_message(
                lead_id=lead.id,
                sender_user_id=actor.id,
                recipient_user_id=lead.user_id,
                message=message.strip(),
                channel="IN_APP",
                delivery_state="queued",
            )
            if lead.status == "NEW":
                self._workflow.validate_transition(from_status="NEW", to_status="IN_PROGRESS")
                lead.status = "IN_PROGRESS"
                self._audit.record_status_transition(
                    lead_id=lead.id,
                    from_status="NEW",
                    to_status="IN_PROGRESS",
                    actor_user_id=actor.id,
                    actor_role=self._role(actor),
                    reason="Auto-promoted after reply",
                )
            lead.last_activity_at = datetime.now(timezone.utc)
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc
        self._notifications.emit_lead_event(
            event_type="lead_reply_sent",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message="Reply delivered via in-app notification",
        )
        self._notifications.emit_email_hook_todo(
            event_type="lead_reply_sent",
            lead_id=str(lead.id),
            recipient_hint=str(lead.user_id) if lead.user_id else None,
        )
        return self._serialize_message(row)

    def list_history(self, *, actor: User, lead_id: UUID) -> list[dict[str, Any]]:
        if self._role(actor) == UserRoles.REGISTERED_USER:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Registered user cannot access lead history")
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_access(actor=actor, lead=lead)
        rows = self._repo.list_status_history(lead_id=lead.id)
        return [self._serialize_history_item(row) for row in rows]

    def _must_get_lead(self, *, lead_id: UUID) -> Lead:
        lead = self._repo.get_lead_by_id(lead_id=lead_id)
        if not lead:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.NOT_FOUND)
        return lead

    def _resolve_property_id(self, property_id: str) -> UUID:
        raw = str(property_id).strip()
        try:
            return UUID(raw)
        except ValueError:
            pass

        if raw.isdigit():
            resolved = self._repo.get_property_id_by_hash(property_hash=int(raw))
            if resolved:
                return resolved
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.PROPERTY_NOT_FOUND)

    def _ensure_access(self, *, actor: User, lead: Lead) -> None:
        try:
            self._permission.ensure_user_can_access_lead(actor=actor, lead=lead)
        except PermissionError as exc:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=str(exc)) from exc

    def _ensure_notes_access_allowed(self, *, actor: User) -> None:
        if self._role(actor) == UserRoles.REGISTERED_USER:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Registered user cannot access lead notes")

    def _property_summary_for_lead(self, lead: Lead) -> Optional[dict[str, Any]]:
        if not lead.property_id:
            return None
        return self._repo.get_property_summaries_by_ids([lead.property_id]).get(lead.property_id)

    def _agent_summary_for_lead(self, lead: Lead) -> Optional[dict[str, Any]]:
        if not lead.assigned_agent_id:
            return None
        return self._repo.get_agent_summaries_by_ids({lead.assigned_agent_id}).get(lead.assigned_agent_id)

    def _user_summary_for_lead(self, lead: Lead) -> Optional[dict[str, Any]]:
        if not lead.user_id:
            return None
        return self._repo.get_user_summaries_by_ids({lead.user_id}).get(lead.user_id)

    @staticmethod
    def _communication_mode(lead: Lead) -> str:
        return str(getattr(lead, "communication_mode", None) or "IN_APP")

    @staticmethod
    def _external_owner_summary(lead: Lead) -> Optional[dict[str, Any]]:
        name = getattr(lead, "external_owner_name", None)
        email = getattr(lead, "external_owner_email", None)
        phone = getattr(lead, "external_owner_phone", None)
        if not any([name, email, phone]):
            return None
        return {"name": name, "email": email, "phone": phone}

    @staticmethod
    def _role(actor: User) -> str:
        roles = {r.name for r in actor.roles}
        if UserRoles.ADMIN in roles:
            return UserRoles.ADMIN
        if UserRoles.AGENT in roles:
            return UserRoles.AGENT
        if UserRoles.REGISTERED_USER in roles:
            return UserRoles.REGISTERED_USER
        return ""

    def _serialize_lead(
        self,
        lead: Lead,
        *,
        property_summary: Optional[dict[str, Any]] = None,
        assigned_agent_summary: Optional[dict[str, Any]] = None,
        user_summary: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        num = getattr(lead, "lead_number", None)
        return {
            "id": str(lead.id),
            "leadNumber": str(num) if num is not None else "",
            "propertyId": str(lead.property_id) if lead.property_id else None,
            "property": property_summary,
            "userId": str(lead.user_id) if lead.user_id else None,
            "user": user_summary,
            "communicationMode": self._communication_mode(lead),
            "externalOwner": self._external_owner_summary(lead),
            "externalPropertyName": getattr(lead, "external_property_name", None),
            "createdByAgentId": str(getattr(lead, "created_by_agent_id", None))
            if getattr(lead, "created_by_agent_id", None)
            else None,
            "status": str(lead.status),
            "source": str(lead.source),
            "assignedAgentId": str(lead.assigned_agent_id) if lead.assigned_agent_id else None,
            "assignedAgent": assigned_agent_summary,
            "assignedByAdminId": str(lead.assigned_by_admin_id) if lead.assigned_by_admin_id else None,
            "message": lead.message,
            "lastActivityAt": lead.last_activity_at,
            "requestCloseAt": lead.request_close_at,
            "closedAt": lead.closed_at,
            "closedByAdminId": str(lead.closed_by_admin_id) if lead.closed_by_admin_id else None,
            "createdAt": lead.created_at,
            "updatedAt": lead.updated_at,
        }

    @staticmethod
    def _serialize_message(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "leadId": str(row.lead_id),
            "senderUserId": str(row.sender_user_id) if row.sender_user_id else None,
            "recipientUserId": str(row.recipient_user_id) if row.recipient_user_id else None,
            "message": row.message,
            "channel": str(row.channel),
            "deliveryState": row.delivery_state,
            "createdAt": row.created_at,
        }

    @staticmethod
    def _serialize_note(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "leadId": str(row.lead_id),
            "authorUserId": str(row.author_user_id) if row.author_user_id else None,
            "note": row.note,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    @staticmethod
    def _serialize_history_item(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "leadId": str(row.lead_id),
            "fromStatus": str(row.from_status) if row.from_status else None,
            "toStatus": str(row.to_status),
            "actorUserId": str(row.actor_user_id) if row.actor_user_id else None,
            "actorRole": row.actor_role,
            "reason": row.reason,
            "changedAt": row.changed_at,
        }
