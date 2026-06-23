from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.schemas.deal_closures import DealClosureCreate, DealClosureReview
from app.services.deal_closures import (
    _assert_can_view,
    create_deal_closure,
    get_deal_closure_or_404,
    list_deal_closures,
    review_deal_closure,
    serialize_deal_closure,
)
from app.utils.api_response import success_response

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.post("")
def request_deal_closure(payload: DealClosureCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    closure = create_deal_closure(
        db,
        payload=payload,
        user_id=context.user_id,
        roles=context.roles,
        agency_id=context.agency_id,
    )
    db.commit()
    db.refresh(closure)
    return success_response(serialize_deal_closure(db, closure), "Deal closure requested successfully")


@router.get("")
def get_deal_closures(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    status: str | None = None,
) -> dict:
    items, pagination = list_deal_closures(
        db,
        user_id=context.user_id,
        roles=context.roles,
        agency_id=context.agency_id,
        page=page,
        page_size=pageSize,
        status=status,
    )
    return success_response({**pagination, "items": items}, meta={"pagination": pagination})


@router.get("/{closure_id}")
def get_deal_closure(closure_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    closure = get_deal_closure_or_404(db, closure_id)
    _assert_can_view(closure, user_id=context.user_id, roles=context.roles, agency_id=context.agency_id)
    return success_response(serialize_deal_closure(db, closure))


@router.post("/{closure_id}/review")
def review_deal_closure_request(
    closure_id: UUID,
    payload: DealClosureReview,
    context: AuthenticatedContext,
    db: DBSessionDep,
) -> dict:
    closure = get_deal_closure_or_404(db, closure_id)
    closure = review_deal_closure(
        db,
        closure=closure,
        action=payload.action,
        reason=payload.reason,
        actor_user_id=context.user_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    db.commit()
    db.refresh(closure)
    return success_response(serialize_deal_closure(db, closure), "Deal closure reviewed successfully")

