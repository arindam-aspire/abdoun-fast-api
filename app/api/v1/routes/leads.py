from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, get_request_context, require_authenticated_user
from app.schemas.leads import (
    LeadAssignRequest,
    LeadCloseRequest,
    LeadCreate,
    LeadMessageCreate,
    LeadNoteCreate,
    LeadStatusUpdateRequest,
)
from app.services.leads import (
    add_lead_message,
    add_lead_note,
    assert_can_access_lead,
    assign_lead,
    create_lead,
    get_lead_or_404,
    list_leads_for_context,
    serialize_lead,
    update_lead_status,
)
from app.utils.api_response import success_response

router = APIRouter()
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.post("")
def create_property_lead(payload: LeadCreate, context: ContextDep, db: DBSessionDep) -> dict:
    lead = create_lead(db, payload=payload, user_id=context.user_id)
    db.commit()
    db.refresh(lead)
    return success_response(serialize_lead(db, lead), "Lead created successfully")


@router.get("")
def list_leads(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    status: str | None = None,
) -> dict:
    items, pagination = list_leads_for_context(
        db,
        user_id=context.user_id,
        roles=context.roles,
        agency_id=context.agency_id,
        page=page,
        page_size=pageSize,
        status=status,
    )
    return success_response({**pagination, "items": items}, meta={"pagination": pagination})


@router.get("/{lead_id}")
def get_lead(lead_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    return success_response(serialize_lead(db, lead))


@router.patch("/{lead_id}/assign")
def assign_lead_to_agent(lead_id: UUID, payload: LeadAssignRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    lead = assign_lead(
        db,
        lead=lead,
        agent_id=payload.agent_id,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    db.commit()
    db.refresh(lead)
    return success_response(serialize_lead(db, lead), "Lead assigned successfully")


@router.patch("/{lead_id}/status")
def change_lead_status(lead_id: UUID, payload: LeadStatusUpdateRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    lead = update_lead_status(
        db,
        lead=lead,
        status=payload.status,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(lead)
    return success_response(serialize_lead(db, lead), "Lead status updated successfully")


@router.post("/{lead_id}/request-close")
def request_lead_close(lead_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    lead = update_lead_status(
        db,
        lead=lead,
        status="REQUEST_FOR_CLOSE",
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        reason="Close requested",
    )
    db.commit()
    db.refresh(lead)
    return success_response(serialize_lead(db, lead), "Lead close requested successfully")


@router.post("/{lead_id}/close")
def close_lead(
    lead_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequest | None = None,
) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    lead = update_lead_status(
        db,
        lead=lead,
        status="CLOSED",
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(lead)
    return success_response(serialize_lead(db, lead), "Lead closed successfully")


@router.post("/{lead_id}/notes")
def create_lead_note(lead_id: UUID, payload: LeadNoteCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    note = add_lead_note(db, lead=lead, author_user_id=context.user_id, note=payload.note)
    db.commit()
    return success_response(
        {
            "id": str(note.id),
            "lead_id": str(note.lead_id),
            "author_user_id": str(note.author_user_id),
            "note": note.note,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        },
        "Lead note added successfully",
    )


@router.post("/{lead_id}/messages")
def create_lead_message(lead_id: UUID, payload: LeadMessageCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    message = add_lead_message(
        db,
        lead=lead,
        sender_user_id=context.user_id,
        recipient_user_id=payload.recipient_user_id,
        message=payload.message,
        channel=payload.channel,
    )
    db.commit()
    return success_response(
        {
            "id": str(message.id),
            "lead_id": str(message.lead_id),
            "sender_user_id": str(message.sender_user_id),
            "recipient_user_id": str(message.recipient_user_id) if message.recipient_user_id else None,
            "message": message.message,
            "channel": message.channel,
            "delivery_state": message.delivery_state,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        },
        "Lead message added successfully",
    )
