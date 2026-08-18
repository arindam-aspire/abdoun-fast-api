from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, get_request_context, require_any_role, require_authenticated_user
from app.schemas.leads import (
    LeadAssignRequest,
    LeadCloseRequest,
    LeadCloseRequestDecision,
    LeadCreate,
    LeadMessageCreate,
    LeadNoteCreate,
    LeadStatusUpdateRequest,
)
from app.services.leads import (
    add_lead_message,
    add_lead_note,
    assert_admin_can_review_close,
    assert_can_access_lead,
    assign_lead,
    approve_lead_close,
    cancel_lead_close_request,
    create_lead_close_request,
    create_lead,
    get_lead_close_request_or_404,
    get_lead_or_404,
    get_pending_lead_close_request,
    list_lead_activity,
    list_lead_close_requests,
    list_lead_messages,
    list_lead_notes,
    list_leads_for_context,
    list_owner_enquiries,
    serialize_lead,
    serialize_lead_close_request,
    serialize_lead_message,
    serialize_lead_note,
    review_lead_close_request,
    update_lead_status,
)
from app.utils.api_response import success_response

router = APIRouter()
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]
OwnerContext = Annotated[RequestContext, Depends(require_any_role("owner", "registered_user"))]


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


@router.get("/my-enquiries")
def get_my_enquiries(
    context: OwnerContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    search: str | None = None,
    status: str | None = None,
    source: str | None = None,
    inquiryType: str | None = None,
    assignedAgentId: UUID | None = None,
    sortBy: str = "updated_at",
    sortOrder: str = "desc",
) -> dict:
    items, pagination = list_owner_enquiries(
        db,
        owner_id=context.user_id,
        page=page,
        page_size=pageSize,
        search=search,
        status=status,
        source=source,
        inquiry_type=inquiryType,
        assigned_agent_id=assignedAgentId,
        sort_by=sortBy,
        sort_order=sortOrder,
    )
    return success_response(
        {**pagination, "items": items, "enquiries": items},
        meta={"pagination": pagination},
    )


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
    if payload.status == "REQUEST_FOR_CLOSE":
        close_request = create_lead_close_request(
            db,
            lead=lead,
            requested_by=context.user_id,
            actor_roles=context.roles,
            reason=payload.reason,
        )
        db.commit()
        db.refresh(lead)
        db.refresh(close_request)
        return success_response(
            {
                **serialize_lead(db, lead),
                "close_request": serialize_lead_close_request(close_request),
            },
            "Lead close request created successfully",
        )
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
def request_lead_close(
    lead_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequest | None = None,
) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    close_request = create_lead_close_request(
        db,
        lead=lead,
        requested_by=context.user_id,
        actor_roles=context.roles,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(lead)
    db.refresh(close_request)
    return success_response(
        {
            **serialize_lead(db, lead),
            "close_request": serialize_lead_close_request(close_request),
        },
        "Lead close request created successfully",
    )


@router.get("/{lead_id}/close-requests")
def get_lead_close_requests(lead_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    return success_response({"items": list_lead_close_requests(db, lead_id=lead.id)})


@router.post("/close-requests/{request_id}/approve")
def approve_lead_close_request(
    request_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequestDecision | None = None,
) -> dict:
    close_request = get_lead_close_request_or_404(db, request_id)
    lead = get_lead_or_404(db, close_request.lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    review_lead_close_request(
        db,
        request=close_request,
        lead=lead,
        approved=True,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(lead)
    db.refresh(close_request)
    return success_response(
        {
            "lead": serialize_lead(db, lead),
            "close_request": serialize_lead_close_request(close_request),
        },
        "Lead close request approved successfully",
    )


@router.post("/close-requests/{request_id}/reject")
def reject_lead_close_request(
    request_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequestDecision | None = None,
) -> dict:
    close_request = get_lead_close_request_or_404(db, request_id)
    lead = get_lead_or_404(db, close_request.lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    review_lead_close_request(
        db,
        request=close_request,
        lead=lead,
        approved=False,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(close_request)
    return success_response(
        {
            "lead": serialize_lead(db, lead),
            "close_request": serialize_lead_close_request(close_request),
        },
        "Lead close request rejected successfully",
    )


@router.post("/close-requests/{request_id}/cancel")
def cancel_pending_lead_close_request(
    request_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequestDecision | None = None,
) -> dict:
    close_request = get_lead_close_request_or_404(db, request_id)
    lead = get_lead_or_404(db, close_request.lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    cancel_lead_close_request(
        db,
        request=close_request,
        lead=lead,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(close_request)
    return success_response(
        {
            "lead": serialize_lead(db, lead),
            "close_request": serialize_lead_close_request(close_request),
        },
        "Lead close request canceled successfully",
    )


@router.post("/{lead_id}/close")
def close_lead(
    lead_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequest | None = None,
) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    close_request = approve_lead_close(
        db,
        lead=lead,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(lead)
    db.refresh(close_request)
    return success_response(
        {
            "lead": serialize_lead(db, lead),
            "close_request": serialize_lead_close_request(close_request),
        },
        "Lead close request approved successfully",
    )


@router.post("/{lead_id}/reject-close")
def reject_lead_close(
    lead_id: UUID,
    context: AuthenticatedContext,
    db: DBSessionDep,
    payload: LeadCloseRequestDecision | None = None,
) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    assert_admin_can_review_close(
        db,
        lead,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    close_request = get_pending_lead_close_request(db, lead_id=lead.id)
    review_lead_close_request(
        db,
        request=close_request,
        lead=lead,
        approved=False,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        reason=payload.reason if payload else None,
    )
    db.commit()
    db.refresh(lead)
    db.refresh(close_request)
    return success_response(
        {
            "lead": serialize_lead(db, lead),
            "close_request": serialize_lead_close_request(close_request),
        },
        "Lead close request rejected successfully",
    )


@router.get("/{lead_id}/notes")
def get_lead_notes(lead_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    items = list_lead_notes(db, lead=lead, user_id=context.user_id, roles=context.roles)
    return success_response({"items": items})


@router.post("/{lead_id}/notes")
def create_lead_note(lead_id: UUID, payload: LeadNoteCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    note = add_lead_note(db, lead=lead, author_user_id=context.user_id, note=payload.note)
    db.commit()
    return success_response(serialize_lead_note(note), "Lead note added successfully")


@router.get("/{lead_id}/activity")
def get_lead_activity(lead_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    items = list_lead_activity(db, lead=lead)
    return success_response({"items": items})


@router.get("/{lead_id}/messages")
def get_lead_messages(lead_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lead = get_lead_or_404(db, lead_id)
    assert_can_access_lead(db, lead, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    items = list_lead_messages(db, lead_id=lead.id)
    return success_response({"items": items})


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
    return success_response(serialize_lead_message(message), "Lead message added successfully")
