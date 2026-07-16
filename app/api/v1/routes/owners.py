from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.api.deps import DBSessionDep, RequestContext, require_any_role
from app.schemas.owners import OwnerDeactivateRequest, OwnerStatusUpdateRequest, OwnerUpdateRequest
from app.services.owners import (
    activate_owner,
    deactivate_owner,
    get_owner,
    list_owner_leads,
    list_owner_properties,
    list_owners,
    update_owner,
    update_owner_status,
)
from app.utils.api_response import raise_api_error, success_response
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_UNAUTHORIZED

router = APIRouter()

OwnerAdminContext = Annotated[RequestContext, Depends(require_any_role("admin", "super_admin"))]


def _actor_user_id(context: RequestContext) -> UUID:
    if context.user_id is None:
        raise_api_error(
            status_code=STATUS_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Authentication is required",
        )
    return context.user_id


@router.get("")
def get_owners(
    context: OwnerAdminContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    sortBy: str = "created_at",
    sortOrder: str = "desc",
    search: str | None = None,
    status: str | None = None,
) -> dict:
    data = list_owners(
        db,
        agency_id=context.agency_id,
        roles=context.roles,
        page=page,
        page_size=pageSize,
        sort_by=sortBy,
        sort_order=sortOrder,
        search=search,
        status=status,
    )
    return success_response(data, meta={"pagination": data["pagination"]})


@router.get("/{owner_id}")
def get_owner_detail(owner_id: UUID, context: OwnerAdminContext, db: DBSessionDep) -> dict:
    owner = get_owner(
        db,
        owner_id=owner_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    return success_response(owner)


@router.patch("/{owner_id}")
def patch_owner(
    owner_id: UUID,
    payload: OwnerUpdateRequest,
    context: OwnerAdminContext,
    db: DBSessionDep,
) -> dict:
    if payload.full_name is None and payload.email is None and payload.phone_number is None:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="At least one field is required to update",
        )
    owner = update_owner(
        db,
        owner_id=owner_id,
        actor_user_id=_actor_user_id(context),
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
    )
    db.commit()
    return success_response(owner, "Owner updated successfully")


@router.patch("/{owner_id}/status")
def set_owner_status(
    owner_id: UUID,
    payload: OwnerStatusUpdateRequest,
    context: OwnerAdminContext,
    db: DBSessionDep,
) -> dict:
    owner = update_owner_status(
        db,
        owner_id=owner_id,
        actor_user_id=_actor_user_id(context),
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        status=payload.status,
        reason=payload.reason,
    )
    db.commit()
    status = str(owner.get("status") or "").upper()
    if status == "ACTIVE":
        message = "Owner activated successfully"
    elif status in {"INACTIVE", "SUSPENDED"}:
        message = "Owner deactivated successfully"
    else:
        message = f"Owner status updated to {status}"
    return success_response(owner, message)


@router.patch("/{owner_id}/activate")
def activate_owner_account(owner_id: UUID, context: OwnerAdminContext, db: DBSessionDep) -> dict:
    owner = activate_owner(
        db,
        owner_id=owner_id,
        actor_user_id=_actor_user_id(context),
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    db.commit()
    return success_response(owner, "Owner activated successfully")


@router.patch("/{owner_id}/deactivate")
def deactivate_owner_account(
    owner_id: UUID,
    context: OwnerAdminContext,
    db: DBSessionDep,
    payload: OwnerDeactivateRequest = Body(default=OwnerDeactivateRequest()),
) -> dict:
    if not payload.confirm:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Deactivation must be confirmed",
        )
    owner = deactivate_owner(
        db,
        owner_id=owner_id,
        actor_user_id=_actor_user_id(context),
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        reason=payload.reason,
    )
    db.commit()
    return success_response(owner, "Owner deactivated successfully")


@router.get("/{owner_id}/properties")
def get_owner_properties(
    owner_id: UUID,
    context: OwnerAdminContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
) -> dict:
    data = list_owner_properties(
        db,
        owner_id=owner_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        page=page,
        page_size=pageSize,
    )
    return success_response(data, meta={"pagination": data["pagination"]})


@router.get("/{owner_id}/leads")
def get_owner_leads(
    owner_id: UUID,
    context: OwnerAdminContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    status: str | None = None,
) -> dict:
    data = list_owner_leads(
        db,
        owner_id=owner_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        page=page,
        page_size=pageSize,
        status=status,
    )
    return success_response(data, meta={"pagination": data["pagination"]})
