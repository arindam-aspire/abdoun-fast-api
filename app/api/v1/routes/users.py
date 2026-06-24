from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.core.config import get_settings
from app.models.live_schema import AgencyMaster, RecentlyViewedProperty
from app.schemas.favorites import RecentViewCreate
from app.schemas.users import AssignUserAgencyRequest
from app.services.auth import get_user_or_404, serialize_user
from app.services.user_agencies import REL_PROPERTY_OWNER, active_mappings, ensure_user_agency_mapping
from app.services.public_properties import (
    get_public_submission_or_404,
    pagination_meta,
    resolve_property_uuid_or_404,
    serialize_property_listing,
    utc_now,
)
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_NOT_FOUND

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.patch("/agency")
def assign_user_agency(payload: AssignUserAgencyRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    agency_id = UUID(payload.agencyId)
    agency = db.get(AgencyMaster, agency_id)
    if not agency or not agency.is_active or not agency.is_verified:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")

    settings = get_settings()
    owner_mappings = active_mappings(db, user_id=user.id, relationship_type=REL_PROPERTY_OWNER)
    if owner_mappings and not settings.allow_owner_multiple_agencies and all(mapping.agency_id != agency.id for mapping in owner_mappings):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Owner is already linked to an agency")

    ensure_user_agency_mapping(
        db,
        user_id=user.id,
        agency_id=agency.id,
        relationship_type=REL_PROPERTY_OWNER,
        actor_user_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return success_response(serialize_user(db, user), "Agency assigned successfully")


@router.get("/recent-views")
def list_recent_views(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
) -> dict:
    page = max(page, 1)
    pageSize = max(min(pageSize, 100), 1)
    stmt = (
        select(RecentlyViewedProperty)
        .where(RecentlyViewedProperty.user_id == context.user_id)
        .order_by(RecentlyViewedProperty.viewed_at.desc())
    )
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    views = db.execute(stmt.offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    items = []
    for view in views:
        try:
            submission, submitter = get_public_submission_or_404(db, view.property_id)
        except HTTPException:
            continue
        property_payload = serialize_property_listing(db, submission, submitter=submitter, user_id=context.user_id)
        items.append(
            {
                "id": str(view.id),
                "user_id": str(view.user_id),
                "property_hash_id": int(property_payload["property_hash"]),
                "property_hash": int(property_payload["property_hash"]),
                "property": property_payload,
            }
        )
    pagination = pagination_meta(total, page, pageSize)
    return success_response({**pagination, "items": items}, meta={"pagination": pagination})


@router.post("/recent-views")
def add_recent_view(payload: RecentViewCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    property_id = resolve_property_uuid_or_404(db, payload.property_hash_id)
    db.execute(
        delete(RecentlyViewedProperty).where(
            RecentlyViewedProperty.user_id == context.user_id,
            RecentlyViewedProperty.property_id == property_id,
        )
    )
    view = RecentlyViewedProperty(
        id=uuid4(),
        user_id=context.user_id,
        property_id=property_id,
        viewed_at=utc_now(),
    )
    db.add(view)
    db.flush()
    submission, submitter = get_public_submission_or_404(db, property_id)
    property_payload = serialize_property_listing(db, submission, submitter=submitter, user_id=context.user_id)
    db.commit()
    return success_response(
        {
            "id": str(view.id),
            "user_id": str(context.user_id),
            "property_hash_id": int(property_payload["property_hash"]),
            "property_hash": int(property_payload["property_hash"]),
            "property": property_payload,
        },
        "Recent view recorded successfully",
    )


@router.delete("/recent-views")
def clear_recent_views(context: AuthenticatedContext, db: DBSessionDep) -> dict:
    db.execute(delete(RecentlyViewedProperty).where(RecentlyViewedProperty.user_id == context.user_id))
    db.commit()
    return success_response(True, "Recent views cleared successfully")


@router.delete("/recent-views/{property_hash_id}")
def remove_recent_view(property_hash_id: int, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    property_id = resolve_property_uuid_or_404(db, property_hash_id)
    db.execute(
        delete(RecentlyViewedProperty).where(
            RecentlyViewedProperty.user_id == context.user_id,
            RecentlyViewedProperty.property_id == property_id,
        )
    )
    db.commit()
    return success_response(True, "Recent view removed successfully")
