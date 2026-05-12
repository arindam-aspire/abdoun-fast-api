"""Lead orchestration service with delegated workflow/permission/audit/notification responsibilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from app.constants.notification_types import NotificationType
from app.models.property_normalized import Lead
from app.models.user import User
from app.repositories.lead_repository import LeadRepository
from app.services.lead_audit_service import LeadAuditService
from app.services.lead_notification_service import LeadNotificationService
from app.services.lead_permission_service import LeadPermissionService
from app.services.lead_workflow_manager import LeadWorkflowManager
from app.services.notification_event_emitter import NotificationEmitPayload, NotificationEventEmitter
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.logger import api_logger
from app.utils.log_messages import format_log_message
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
        notification_emitter: NotificationEventEmitter | None = None,
    ) -> None:
        self._repo = repo
        self._workflow = workflow
        self._permission = permission
        self._audit = audit
        self._notifications = notifications
        self._notification_emitter = notification_emitter

    def _emit_lead_notification_batch(
        self,
        *,
        payloads: list[NotificationEmitPayload],
        log_context: str,
        entity_id: str,
    ) -> None:
        if self._notification_emitter is None or not payloads:
            return
        try:
            self._notification_emitter.emit_bulk(payloads=payloads)
        except Exception as exc:
            api_logger.error(
                format_log_message(
                    "Lead notification dispatch failed context={ctx} entity_id={eid} error={err}",
                    ctx=log_context,
                    eid=entity_id,
                    err=str(exc),
                ),
                exc_info=True,
            )

    def _emit_lead_notification_single(
        self,
        *,
        payload: NotificationEmitPayload,
        log_context: str,
        entity_id: str,
    ) -> None:
        if self._notification_emitter is None:
            return
        try:
            self._notification_emitter.emit(payload=payload)
        except Exception as exc:
            api_logger.error(
                format_log_message(
                    "Lead notification dispatch failed context={ctx} entity_id={eid} error={err}",
                    ctx=log_context,
                    eid=entity_id,
                    err=str(exc),
                ),
                exc_info=True,
            )

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

        # In-app notifications: separate commits via NotificationEventEmitter (after lead txn succeeds).
        self._notify_contact_form_lead_created(
            lead=lead,
            actor=actor,
            assigned_agent_id=assigned_agent_id,
            resolved_property_id=resolved_property_id,
        )

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

    def _notify_contact_form_lead_created(
        self,
        *,
        lead: Lead,
        actor: User,
        assigned_agent_id: UUID,
        resolved_property_id: UUID,
    ) -> None:
        """Notify assigned agent, lead owner, and admins; dedupes shared identities."""
        if self._notification_emitter is None:
            return

        prop_summary = self._repo.get_property_summaries_by_ids([resolved_property_id]).get(resolved_property_id) or {}
        title = (prop_summary.get("title") or "").strip() if isinstance(prop_summary, dict) else ""
        lead_num = (getattr(lead, "lead_number", None) or "").strip()
        lead_name = title or lead_num or "Lead"
        lead_id_display = lead_num or str(lead.id)

        creator_raw = getattr(actor, "full_name", None)
        creator_name = str(creator_raw).strip() if creator_raw is not None else ""
        if not creator_name:
            creator_name = "Unknown"

        recipient_ids: list[UUID] = [assigned_agent_id, actor.id]
        recipient_ids.extend(self._repo.list_active_user_ids_with_role(role_name=UserRoles.ADMIN))
        unique_recipients = list(dict.fromkeys(recipient_ids))

        roles_by_user = self._repo.get_role_names_by_user_ids(set(unique_recipients))
        et = NotificationType.LEAD_CREATED.value
        lead_uuid_str = str(lead.id)

        payloads: list[NotificationEmitPayload] = []
        for recipient_user_id in unique_recipients:
            role_names = roles_by_user.get(recipient_user_id) or set()
            payloads.append(
                NotificationEmitPayload(
                    event_type=et,
                    type_key=et,
                    recipient_user_id=recipient_user_id,
                    actor_user_id=actor.id,
                    recipient_role_names=frozenset(role_names),
                    template_data={
                        "lead_name": lead_name,
                        "lead_id": lead_id_display,
                        "creator_name": creator_name,
                        "entity_type": "lead",
                        "entity_id": lead_uuid_str,
                        "metadata": {
                            "lead_id": lead_uuid_str,
                            "lead_number": lead_num or None,
                        },
                    },
                    idempotency_key=f"lead.created:{lead_uuid_str}:{recipient_user_id}",
                )
            )
        self._emit_lead_notification_batch(
            payloads=payloads,
            log_context="contact_form_lead_created",
            entity_id=lead_uuid_str,
        )

    def _notify_manual_lead_created(
        self,
        *,
        lead: Lead,
        actor: User,
        assigned_agent_id: UUID,
        contact_user_id: Optional[UUID],
        property_id: UUID,
    ) -> None:
        """Notify agent, admin creator, linked contact user, and admins (same routing family as offline)."""
        if self._notification_emitter is None:
            return

        prop_summary = self._repo.get_property_summaries_by_ids([property_id]).get(property_id) or {}
        title = (prop_summary.get("title") or "").strip() if isinstance(prop_summary, dict) else ""
        lead_num = (getattr(lead, "lead_number", None) or "").strip()
        lead_name = title or lead_num or "Lead"
        lead_id_display = lead_num or str(lead.id)
        lead_uuid_str = str(lead.id)

        creator_raw = getattr(actor, "full_name", None)
        creator_name = str(creator_raw).strip() if creator_raw is not None else ""
        if not creator_name:
            creator_name = "Unknown"

        recipient_ids: list[UUID] = [assigned_agent_id, actor.id]
        if contact_user_id is not None:
            recipient_ids.append(contact_user_id)
        recipient_ids.extend(self._repo.list_active_user_ids_with_role(role_name=UserRoles.ADMIN))
        unique_recipients = list(dict.fromkeys(recipient_ids))
        roles_by_user = self._repo.get_role_names_by_user_ids(set(unique_recipients))
        et = NotificationType.LEAD_MANUAL_CREATED.value

        payloads: list[NotificationEmitPayload] = []
        for recipient_user_id in unique_recipients:
            role_names = roles_by_user.get(recipient_user_id) or set()
            payloads.append(
                NotificationEmitPayload(
                    event_type=et,
                    type_key=et,
                    recipient_user_id=recipient_user_id,
                    actor_user_id=actor.id,
                    recipient_role_names=frozenset(role_names),
                    template_data={
                        "lead_name": lead_name,
                        "lead_id": lead_id_display,
                        "creator_name": creator_name,
                        "entity_type": "lead",
                        "entity_id": lead_uuid_str,
                        "metadata": {
                            "lead_id": lead_uuid_str,
                            "lead_number": lead_num or None,
                        },
                    },
                    idempotency_key=f"lead.manual_created:{lead_uuid_str}:{recipient_user_id}",
                )
            )
        self._emit_lead_notification_batch(
            payloads=payloads,
            log_context="admin_manual_lead_created",
            entity_id=lead_uuid_str,
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
        self._notify_manual_lead_created(
            lead=lead,
            actor=actor,
            assigned_agent_id=assigned_agent_id,
            contact_user_id=contact_user_id,
            property_id=property_id,
        )
        return self._serialize_lead(
            lead,
            property_summary=self._property_summary_for_lead(lead),
            assigned_agent_summary=self._agent_summary_for_lead(lead),
            user_summary=self._user_summary_for_lead(lead),
        )

    def create_offline_lead(
        self,
        *,
        actor: User,
        payload: Any,
    ) -> dict[str, Any]:
        role = self._role(actor)
        if role not in {UserRoles.AGENT, UserRoles.ADMIN}:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)

        assigned_agent_id = actor.id
        created_by_agent_id = actor.id
        created_by_admin_id = None
        if role == UserRoles.ADMIN:
            if not payload.assignedAgentId:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="assignedAgentId is required for admin offline lead creation")
            self._permission.ensure_admin_can_manage_agent(admin_user=actor, agent_id=payload.assignedAgentId)
            assigned_agent_id = payload.assignedAgentId
            created_by_agent_id = None
            created_by_admin_id = actor.id
        elif payload.assignedAgentId and payload.assignedAgentId != actor.id:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.UNAUTHORIZED_ACCESS)

        normalized_phone = self._normalize_phone(payload.phoneNumber)
        duplicate = self._repo.find_duplicate_offline_lead(
            phone_number=normalized_phone,
            property_id=payload.propertyId,
            property_name=payload.propertyName,
        )
        if duplicate:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="A lead already exists for this phone and property.",
            )

        now = datetime.now(timezone.utc)
        lead_number = self._repo.allocate_next_lead_number()
        customer_name = payload.customerName.strip()
        property_name = payload.propertyName.strip() if payload.propertyName else None
        notes = payload.notes.strip() if payload.notes else None
        lead = Lead(
            property_id=payload.propertyId,
            user_id=None,
            inquiry_type=payload.inquiryType,
            source="OFFLINE_MANUAL",
            status="NEW",
            assigned_agent_id=assigned_agent_id,
            assigned_by_admin_id=actor.id if role == UserRoles.ADMIN else None,
            message=notes or f"Offline lead created for {customer_name}",
            last_activity_at=now,
            lead_number=lead_number,
            external_owner_name=customer_name,
            external_owner_phone=normalized_phone,
            external_owner_email=None,
            external_property_name=property_name,
            communication_mode="EXTERNAL",
            created_by_agent_id=created_by_agent_id,
            created_by_admin_id=created_by_admin_id,
            offline_inquiry_type=payload.inquiryType,
            offline_source=payload.source,
            offline_notes=notes,
        )
        try:
            self._repo.create_lead(lead=lead)
            self._audit.record_status_transition(
                lead_id=lead.id,
                from_status=None,
                to_status="NEW",
                actor_user_id=actor.id,
                actor_role=role,
                reason="Offline lead created",
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.INTERNAL_SERVER_ERROR) from exc

        # In-app notifications after lead commit (same payload shape as contact-form leads).
        self._notify_offline_lead_created(
            lead=lead,
            actor=actor,
            assigned_agent_id=assigned_agent_id,
            customer_name=customer_name,
            property_name=property_name,
        )

        self._notifications.emit_lead_event(
            event_type="offline_lead_created",
            lead_id=str(lead.id),
            actor_user_id=str(actor.id),
            message="Offline lead created",
        )
        self._notifications.emit_email_hook_todo(
            event_type="offline_lead_created",
            lead_id=str(lead.id),
            recipient_hint=str(assigned_agent_id),
        )
        return self._serialize_lead(
            lead,
            property_summary=self._property_summary_for_lead(lead),
            assigned_agent_summary=self._agent_summary_for_lead(lead),
        )

    def _notify_offline_lead_created(
        self,
        *,
        lead: Lead,
        actor: User,
        assigned_agent_id: UUID,
        customer_name: str,
        property_name: Optional[str],
    ) -> None:
        """Notify agent, creator, linked lead owner (registered user), and admins; dedupes by user id."""
        if self._notification_emitter is None:
            return

        lead_num = (getattr(lead, "lead_number", None) or "").strip()
        lead_uuid_str = str(lead.id)
        lead_id_display = lead_num or lead_uuid_str

        lead_name = (property_name or "").strip() if property_name else ""
        if not lead_name and lead.property_id:
            prop_summary = self._repo.get_property_summaries_by_ids([lead.property_id]).get(lead.property_id) or {}
            if isinstance(prop_summary, dict):
                lead_name = (prop_summary.get("title") or "").strip()
        if not lead_name:
            lead_name = (customer_name or "").strip() or lead_num or "Lead"

        creator_raw = getattr(actor, "full_name", None)
        creator_name = str(creator_raw).strip() if creator_raw is not None else ""
        if not creator_name:
            creator_name = "Unknown"

        recipient_ids: list[UUID] = [assigned_agent_id, actor.id]
        owner_id = getattr(lead, "user_id", None)
        if owner_id is not None:
            recipient_ids.append(owner_id)
        recipient_ids.extend(self._repo.list_active_user_ids_with_role(role_name=UserRoles.ADMIN))
        unique_recipients = list(dict.fromkeys(recipient_ids))

        roles_by_user = self._repo.get_role_names_by_user_ids(set(unique_recipients))
        et = NotificationType.LEAD_OFFLINE_CREATED.value

        payloads: list[NotificationEmitPayload] = []
        for recipient_user_id in unique_recipients:
            role_names = roles_by_user.get(recipient_user_id) or set()
            payloads.append(
                NotificationEmitPayload(
                    event_type=et,
                    type_key=et,
                    recipient_user_id=recipient_user_id,
                    actor_user_id=actor.id,
                    recipient_role_names=frozenset(role_names),
                    template_data={
                        "lead_name": lead_name,
                        "lead_id": lead_id_display,
                        "creator_name": creator_name,
                        "entity_type": "lead",
                        "entity_id": lead_uuid_str,
                        "metadata": {
                            "lead_id": lead_uuid_str,
                            "lead_number": lead_num or None,
                        },
                    },
                    idempotency_key=f"lead.offline_created:{lead_uuid_str}:{recipient_user_id}",
                )
            )
        self._emit_lead_notification_batch(
            payloads=payloads,
            log_context="offline_lead_created",
            entity_id=lead_uuid_str,
        )

    def _notify_lead_in_app_message_recipient(
        self,
        *,
        lead: Lead,
        recipient_user_id: UUID,
        actor: User,
        type_key: str,
        idempotency_key: str,
    ) -> None:
        """Notify lead counterparty (e.g. registered owner)."""
        if self._notification_emitter is None:
            return

        lead_num = (getattr(lead, "lead_number", None) or "").strip()
        lead_uuid_str = str(lead.id)
        lead_id_display = lead_num or lead_uuid_str

        lead_name = "Lead"
        if lead.property_id:
            prop_summary = self._repo.get_property_summaries_by_ids([lead.property_id]).get(lead.property_id) or {}
            if isinstance(prop_summary, dict):
                title = (prop_summary.get("title") or "").strip()
                if title:
                    lead_name = title

        sender_raw = getattr(actor, "full_name", None)
        sender_name = str(sender_raw).strip() if sender_raw is not None else ""
        if not sender_name:
            sender_name = "Unknown"

        roles_by_user = self._repo.get_role_names_by_user_ids({recipient_user_id})
        role_names = roles_by_user.get(recipient_user_id) or set()

        payload = NotificationEmitPayload(
            event_type=type_key,
            type_key=type_key,
            recipient_user_id=recipient_user_id,
            actor_user_id=actor.id,
            recipient_role_names=frozenset(role_names),
            template_data={
                "lead_name": lead_name,
                "lead_id": lead_id_display,
                "sender_name": sender_name,
                "entity_type": "lead",
                "entity_id": lead_uuid_str,
                "metadata": {
                    "lead_id": lead_uuid_str,
                    "lead_number": lead_num or None,
                },
            },
            idempotency_key=idempotency_key,
        )
        self._emit_lead_notification_single(
            payload=payload,
            log_context="lead_in_app_message",
            entity_id=lead_uuid_str,
        )

    def _notify_lead_status_changed_stakeholders(
        self,
        *,
        lead: Lead,
        actor: User,
        previous_status: str,
        new_status: str,
    ) -> None:
        """Notify lead owner, assigned agent, and admins (deduped); excludes actor."""
        if self._notification_emitter is None:
            return

        lead_num = (getattr(lead, "lead_number", None) or "").strip()
        lead_uuid_str = str(lead.id)
        lead_id_display = lead_num or lead_uuid_str

        lead_name = "Lead"
        if lead.property_id:
            prop_summary = self._repo.get_property_summaries_by_ids([lead.property_id]).get(lead.property_id) or {}
            if isinstance(prop_summary, dict):
                title = (prop_summary.get("title") or "").strip()
                if title:
                    lead_name = title

        actor_raw = getattr(actor, "full_name", None)
        actor_name = str(actor_raw).strip() if actor_raw is not None else ""
        if not actor_name:
            actor_name = "Unknown"

        recipient_ids: list[UUID] = []
        if getattr(lead, "user_id", None) is not None:
            recipient_ids.append(lead.user_id)
        if getattr(lead, "assigned_agent_id", None) is not None:
            recipient_ids.append(lead.assigned_agent_id)
        recipient_ids.extend(self._repo.list_active_user_ids_with_role(role_name=UserRoles.ADMIN))

        unique_recipients = list(dict.fromkeys(rid for rid in recipient_ids if rid != actor.id))
        if not unique_recipients:
            return

        roles_by_user = self._repo.get_role_names_by_user_ids(set(unique_recipients))
        et = NotificationType.LEAD_STATUS_CHANGED.value

        payloads: list[NotificationEmitPayload] = []
        for recipient_user_id in unique_recipients:
            role_names = roles_by_user.get(recipient_user_id) or set()
            payloads.append(
                NotificationEmitPayload(
                    event_type=et,
                    type_key=et,
                    recipient_user_id=recipient_user_id,
                    actor_user_id=actor.id,
                    recipient_role_names=frozenset(role_names),
                    template_data={
                        "lead_name": lead_name,
                        "lead_id": lead_id_display,
                        "previous_status": previous_status,
                        "new_status": new_status,
                        "actor_name": actor_name,
                        "entity_type": "lead",
                        "entity_id": lead_uuid_str,
                        "metadata": {
                            "lead_id": lead_uuid_str,
                            "lead_number": lead_num or None,
                            "previous_status": previous_status,
                            "new_status": new_status,
                        },
                    },
                    idempotency_key=f"lead.status_changed:{lead_uuid_str}:{recipient_user_id}:{previous_status}:{new_status}",
                )
            )
        self._emit_lead_notification_batch(
            payloads=payloads,
            log_context="lead_status_changed",
            entity_id=lead_uuid_str,
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
            "summary": self._status_summary(scope="agent", actor_id=actor.id, source=source),
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
            "summary": self._status_summary(scope="admin", source=source),
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
            "summary": self._status_summary(scope="user", actor_id=actor.id, source=source),
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
        self._ensure_lead_is_mutable(lead)
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

        self._notify_lead_status_changed_stakeholders(
            lead=lead,
            actor=actor,
            previous_status=previous_status,
            new_status=to_status,
        )

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
        self._ensure_lead_is_mutable(lead)
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

        # In-app: notify old and new assigned agents only (separate commits via NotificationEventEmitter).
        self._notify_lead_reassign_agents(
            lead=lead,
            actor=actor,
            old_agent_id=old_agent_id,
            new_agent_id=new_agent_id,
        )

        return self._serialize_lead(lead, property_summary=self._property_summary_for_lead(lead))

    def _notify_lead_reassign_agents(
        self,
        *,
        lead: Lead,
        actor: User,
        old_agent_id: Optional[UUID],
        new_agent_id: UUID,
    ) -> None:
        """Notify previous and new assignees only."""
        if self._notification_emitter is None:
            return
        if old_agent_id == new_agent_id:
            return

        lead_num = (getattr(lead, "lead_number", None) or "").strip()
        lead_uuid_str = str(lead.id)
        lead_id_display = lead_num or lead_uuid_str

        prop_summary = self._property_summary_for_lead(lead)
        lead_name = "Lead"
        if isinstance(prop_summary, dict):
            lead_name = (prop_summary.get("title") or "").strip() or lead_name
        if lead_name == "Lead" and lead_num:
            lead_name = lead_num

        admin_raw = getattr(actor, "full_name", None)
        admin_name = str(admin_raw).strip() if admin_raw is not None else ""
        if not admin_name:
            admin_name = "Unknown"

        agent_roles = frozenset({UserRoles.AGENT})
        payloads: list[NotificationEmitPayload] = []

        if old_agent_id is not None and old_agent_id != new_agent_id:
            tk = NotificationType.LEAD_REASSIGN_PREVIOUS_ASSIGNEE.value
            payloads.append(
                NotificationEmitPayload(
                    event_type=tk,
                    type_key=tk,
                    recipient_user_id=old_agent_id,
                    actor_user_id=actor.id,
                    recipient_role_names=agent_roles,
                    template_data={
                        "lead_name": lead_name,
                        "lead_id": lead_id_display,
                        "admin_name": admin_name,
                        "entity_type": "lead",
                        "entity_id": lead_uuid_str,
                        "metadata": {
                            "lead_id": lead_uuid_str,
                            "lead_number": lead_num or None,
                        },
                    },
                    idempotency_key=f"lead.reassign_previous:{lead_uuid_str}:{old_agent_id}:{new_agent_id}",
                )
            )

        tk_new = NotificationType.LEAD_REASSIGN_NEW_ASSIGNEE.value
        payloads.append(
            NotificationEmitPayload(
                event_type=tk_new,
                type_key=tk_new,
                recipient_user_id=new_agent_id,
                actor_user_id=actor.id,
                recipient_role_names=agent_roles,
                template_data={
                    "lead_name": lead_name,
                    "lead_id": lead_id_display,
                    "admin_name": admin_name,
                    "entity_type": "lead",
                    "entity_id": lead_uuid_str,
                    "metadata": {
                        "lead_id": lead_uuid_str,
                        "lead_number": lead_num or None,
                    },
                },
                idempotency_key=f"lead.reassign_new:{lead_uuid_str}:{new_agent_id}:{old_agent_id or 'none'}",
            )
        )
        self._emit_lead_notification_batch(
            payloads=payloads,
            log_context="lead_reassign",
            entity_id=lead_uuid_str,
        )

    def add_note(self, *, actor: User, lead_id: UUID, note: str) -> dict[str, Any]:
        lead = self._must_get_lead(lead_id=lead_id)
        self._ensure_notes_access_allowed(actor=actor)
        self._ensure_access(actor=actor, lead=lead)
        self._ensure_lead_is_mutable(lead)
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
        self._ensure_lead_is_mutable(lead)
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
        self._ensure_lead_is_mutable(lead)
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
        self._ensure_lead_is_mutable(lead)
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

        # Role-based recipients for in-app message notifications.
        # - REGISTERED_USER sender -> assigned agent + admins
        # - AGENT sender -> registered user + admins
        # - ADMIN/other sender -> registered user + assigned agent + admins
        sender_role = self._role(actor)
        recipient_ids: list[UUID] = []
        if sender_role == UserRoles.REGISTERED_USER:
            if lead.assigned_agent_id is not None:
                recipient_ids.append(lead.assigned_agent_id)
        elif sender_role == UserRoles.AGENT:
            if lead.user_id is not None:
                recipient_ids.append(lead.user_id)
        else:
            if lead.user_id is not None:
                recipient_ids.append(lead.user_id)
            if lead.assigned_agent_id is not None:
                recipient_ids.append(lead.assigned_agent_id)

        recipient_ids.extend(self._repo.list_active_user_ids_with_role(role_name=UserRoles.ADMIN))

        for recipient_user_id in dict.fromkeys(recipient_ids):
            if recipient_user_id == actor.id:
                continue
            self._notify_lead_in_app_message_recipient(
                lead=lead,
                recipient_user_id=recipient_user_id,
                actor=actor,
                type_key=NotificationType.LEAD_REPLY_ADDED.value,
                idempotency_key=f"lead.reply_added:{lead.id}:{recipient_user_id}:{row.id}",
            )

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

    @staticmethod
    def _ensure_lead_is_mutable(lead: Lead) -> None:
        if str(lead.status) == "CLOSED":
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Closed leads are read-only.")

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

    def _status_summary(
        self,
        *,
        scope: str,
        actor_id: Optional[UUID] = None,
        source: Optional[str] = None,
    ) -> dict[str, int]:
        statuses = ("NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED")
        default_summary = {"total": 0, **{status: 0 for status in statuses}}
        raw = self._repo.get_lead_status_summary(scope=scope, actor_id=actor_id, source=source)
        if not isinstance(raw, dict):
            return default_summary
        summary = default_summary.copy()
        for key in summary:
            summary[key] = int(raw.get(key, 0) or 0)
        return summary

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
    def _offline_lead_summary(lead: Lead) -> Optional[dict[str, Any]]:
        if str(getattr(lead, "source", "")) not in {"OFFLINE_MANUAL", "AGENT_MANUAL"}:
            return None
        inquiry_type = getattr(lead, "offline_inquiry_type", None) or getattr(lead, "inquiry_type", None)
        offline_source = getattr(lead, "offline_source", None)
        if not any(
            [
                getattr(lead, "external_owner_name", None),
                getattr(lead, "external_owner_phone", None),
                getattr(lead, "external_property_name", None),
                inquiry_type,
                offline_source,
                getattr(lead, "offline_notes", None),
                getattr(lead, "created_by_agent_id", None),
                getattr(lead, "created_by_admin_id", None),
            ]
        ):
            return None
        return {
            "customerName": getattr(lead, "external_owner_name", None),
            "phoneNumber": getattr(lead, "external_owner_phone", None),
            "propertyName": getattr(lead, "external_property_name", None),
            "propertyId": str(lead.property_id) if lead.property_id else None,
            "inquiryType": inquiry_type,
            "source": offline_source,
            "notes": getattr(lead, "offline_notes", None),
            "createdByAgentId": str(getattr(lead, "created_by_agent_id", None))
            if getattr(lead, "created_by_agent_id", None)
            else None,
            "createdByAdminId": str(getattr(lead, "created_by_admin_id", None))
            if getattr(lead, "created_by_admin_id", None)
            else None,
        }

    @staticmethod
    def _normalize_phone(value: str) -> str:
        raw = str(value or "").strip()
        prefix = "+" if raw.startswith("+") else ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        return f"{prefix}{digits}" if digits else raw

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
            "createdByAdminId": str(getattr(lead, "created_by_admin_id", None))
            if getattr(lead, "created_by_admin_id", None)
            else None,
            "offlineLead": self._offline_lead_summary(lead),
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
