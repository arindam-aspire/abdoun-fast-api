"""Canonical lead routes grouped by user/admin/agent scopes."""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.core.auth import get_current_user
from app.api.v1.deps.leads import get_lead_service
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.lead import (
    AdminManualLeadCreateRequest,
    ContactFormLeadCreateRequest,
    LeadItemResponse,
    LeadListResponse,
    LeadNoteCreateRequest,
    LeadNotesResponse,
    LeadNoteResponse,
    LeadNoteUpdateRequest,
    LeadReassignRequest,
    LeadReplyRequest,
    LeadReplyResponse,
    LeadMessagesResponse,
    LeadHistoryItemResponse,
    LeadHistoryResponse,
    OfflineLeadCreateRequest,
    LeadStatusUpdateRequest,
)
from app.services.lead_service import LeadService
from app.utils.constants import SuccessMessages, UserRoles
from app.utils.responses import StandardResponse, create_success_response

public_router = APIRouter()
agent_router = APIRouter()
admin_router = APIRouter()


@public_router.post("/leads/contact-form")
def create_contact_form_lead(
    body: ContactFormLeadCreateRequest,
    current_user: Annotated[User, require_role(UserRoles.REGISTERED_USER)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.create_contact_form_lead(
        actor=current_user,
        property_id=body.propertyId,
        message=body.message,
    )
    return create_success_response(data=LeadItemResponse(**data), message="Your inquiry has been sent successfully")


@public_router.get("/leads/my")
def list_my_leads(
    current_user: Annotated[User, require_role(UserRoles.REGISTERED_USER)],
    service: Annotated[LeadService, Depends(get_lead_service)],
    status: Annotated[Optional[str], Query()] = None,
    source: Annotated[Optional[str], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> StandardResponse[LeadListResponse]:
    data = service.list_my_leads(
        actor=current_user,
        status=status,
        source=source,
        page=page,
        page_size=page_size,
    )
    return create_success_response(data=LeadListResponse(**data), message=None)


@public_router.post("/leads/manual")
def create_offline_lead(
    body: OfflineLeadCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.create_offline_lead(
        actor=current_user,
        payload=body,
    )
    return create_success_response(data=LeadItemResponse(**data), message="Offline lead created")


@public_router.get("/leads/{lead_id}")
def get_lead_detail(
    lead_id: Annotated[UUID, Path()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.get_lead_detail(actor=current_user, lead_id=lead_id)
    return create_success_response(data=LeadItemResponse(**data), message=None)


@public_router.get("/leads/{lead_id}/messages")
def list_lead_messages(
    lead_id: Annotated[UUID, Path()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadMessagesResponse]:
    items = service.list_messages(actor=current_user, lead_id=lead_id)
    return create_success_response(
        data=LeadMessagesResponse(items=[LeadReplyResponse(**item) for item in items]),
        message=None,
    )


@public_router.post("/leads/{lead_id}/messages")
def post_lead_message(
    lead_id: Annotated[UUID, Path()],
    body: LeadReplyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadReplyResponse]:
    data = service.post_message(actor=current_user, lead_id=lead_id, message=body.message)
    return create_success_response(data=LeadReplyResponse(**data), message="Lead reply sent")


@public_router.get("/leads/{lead_id}/notes")
def list_lead_notes(
    lead_id: Annotated[UUID, Path()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadNotesResponse]:
    items = service.list_notes(actor=current_user, lead_id=lead_id)
    return create_success_response(
        data=LeadNotesResponse(items=[LeadNoteResponse(**item) for item in items]),
        message=None,
    )


@public_router.post("/leads/{lead_id}/notes")
def add_lead_note(
    lead_id: Annotated[UUID, Path()],
    body: LeadNoteCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadNoteResponse]:
    data = service.add_note(actor=current_user, lead_id=lead_id, note=body.note)
    return create_success_response(data=LeadNoteResponse(**data), message="Note added")


@public_router.patch("/leads/{lead_id}/notes/{note_id}")
def update_lead_note(
    lead_id: Annotated[UUID, Path()],
    note_id: Annotated[UUID, Path()],
    body: LeadNoteUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadNoteResponse]:
    data = service.update_note(actor=current_user, lead_id=lead_id, note_id=note_id, note=body.note)
    return create_success_response(data=LeadNoteResponse(**data), message="Note updated")


@public_router.delete("/leads/{lead_id}/notes/{note_id}")
def delete_lead_note(
    lead_id: Annotated[UUID, Path()],
    note_id: Annotated[UUID, Path()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[bool]:
    removed = service.delete_note(actor=current_user, lead_id=lead_id, note_id=note_id)
    return create_success_response(data=removed, message="Note deleted")


@public_router.get("/leads/{lead_id}/history")
def get_lead_history(
    lead_id: Annotated[UUID, Path()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadHistoryResponse]:
    items = service.list_history(actor=current_user, lead_id=lead_id)
    return create_success_response(
        data=LeadHistoryResponse(items=[LeadHistoryItemResponse(**item) for item in items]),
        message=None,
    )


@agent_router.get("/leads")
def list_agent_leads(
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
    status: Annotated[Optional[str], Query()] = None,
    source: Annotated[Optional[str], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> StandardResponse[LeadListResponse]:
    data = service.list_agent_leads(
        actor=current_user,
        status=status,
        source=source,
        page=page,
        page_size=page_size,
    )
    return create_success_response(data=LeadListResponse(**data), message=None)


@agent_router.get("/leads/{lead_id}")
def get_agent_lead_detail(
    lead_id: Annotated[UUID, Path()],
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.get_lead_detail(actor=current_user, lead_id=lead_id)
    return create_success_response(data=LeadItemResponse(**data), message=None)


@agent_router.patch("/leads/{lead_id}/status")
def update_agent_lead_status(
    lead_id: Annotated[UUID, Path()],
    body: LeadStatusUpdateRequest,
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.update_status(actor=current_user, lead_id=lead_id, to_status=body.status, reason=body.reason)
    return create_success_response(data=LeadItemResponse(**data), message=SuccessMessages.AGENT_STATUS_UPDATED)


@agent_router.post("/leads/{lead_id}/reply")
def reply_to_lead_as_agent(
    lead_id: Annotated[UUID, Path()],
    body: LeadReplyRequest,
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadReplyResponse]:
    data = service.post_message(actor=current_user, lead_id=lead_id, message=body.message)
    return create_success_response(data=LeadReplyResponse(**data), message="Lead reply sent")


@agent_router.post("/leads/{lead_id}/notes")
def add_lead_note_as_agent(
    lead_id: Annotated[UUID, Path()],
    body: LeadNoteCreateRequest,
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadNoteResponse]:
    data = service.add_note(actor=current_user, lead_id=lead_id, note=body.note)
    return create_success_response(data=LeadNoteResponse(**data), message="Note added")


@agent_router.patch("/leads/{lead_id}/notes/{note_id}")
def update_lead_note_as_agent(
    lead_id: Annotated[UUID, Path()],
    note_id: Annotated[UUID, Path()],
    body: LeadNoteUpdateRequest,
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadNoteResponse]:
    data = service.update_note(actor=current_user, lead_id=lead_id, note_id=note_id, note=body.note)
    return create_success_response(data=LeadNoteResponse(**data), message="Note updated")


@agent_router.delete("/leads/{lead_id}/notes/{note_id}")
def delete_lead_note_as_agent(
    lead_id: Annotated[UUID, Path()],
    note_id: Annotated[UUID, Path()],
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[bool]:
    removed = service.delete_note(actor=current_user, lead_id=lead_id, note_id=note_id)
    return create_success_response(data=removed, message="Note deleted")


@admin_router.get("/leads")
def list_admin_leads(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[LeadService, Depends(get_lead_service)],
    status: Annotated[Optional[str], Query()] = None,
    source: Annotated[Optional[str], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> StandardResponse[LeadListResponse]:
    data = service.list_admin_leads(
        actor=current_user,
        status=status,
        source=source,
        page=page,
        page_size=page_size,
    )
    return create_success_response(data=LeadListResponse(**data), message=None)


@admin_router.post("/leads")
def create_admin_manual_lead(
    body: AdminManualLeadCreateRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.create_admin_manual_lead(
        actor=current_user,
        property_id=body.propertyId,
        assigned_agent_id=body.assignedAgentId,
        source=body.source,
        message=body.message,
        contact_user_id=body.contactUserId,
    )
    return create_success_response(data=LeadItemResponse(**data), message="Lead created")


@admin_router.patch("/leads/{lead_id}/reassign")
def reassign_lead_by_admin(
    lead_id: Annotated[UUID, Path()],
    body: LeadReassignRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.reassign_lead(actor=current_user, lead_id=lead_id, new_agent_id=body.assignedAgentId)
    return create_success_response(data=LeadItemResponse(**data), message="Lead reassigned")


@admin_router.patch("/leads/{lead_id}/status")
def update_admin_lead_status(
    lead_id: Annotated[UUID, Path()],
    body: LeadStatusUpdateRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.update_status(actor=current_user, lead_id=lead_id, to_status=body.status, reason=body.reason)
    return create_success_response(data=LeadItemResponse(**data), message=SuccessMessages.AGENT_STATUS_UPDATED)


@admin_router.post("/leads/{lead_id}/close-decision")
def close_decision_by_admin(
    lead_id: Annotated[UUID, Path()],
    body: LeadStatusUpdateRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> StandardResponse[LeadItemResponse]:
    data = service.update_status(actor=current_user, lead_id=lead_id, to_status=body.status, reason=body.reason)
    return create_success_response(data=LeadItemResponse(**data), message="Close decision applied")
