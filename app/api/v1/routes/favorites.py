from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.models.live_schema import UserPropertyFavorite
from app.schemas.favorites import FavoriteCreate
from app.services.public_properties import (
    favorite_lookup,
    get_public_submission_or_404,
    pagination_meta,
    resolve_property_uuid_or_404,
    serialize_property_listing,
    utc_now,
)
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_BAD_REQUEST

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.get("")
def list_favorites(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
) -> dict:
    page = max(page, 1)
    pageSize = max(min(pageSize, 100), 1)
    stmt = (
        select(UserPropertyFavorite)
        .where(UserPropertyFavorite.user_id == context.user_id)
        .order_by(UserPropertyFavorite.created_at.desc())
    )
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    favorites = db.execute(stmt.offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    items = []
    for favorite in favorites:
        try:
            match = get_public_submission_or_404(db, favorite.property_id)
        except HTTPException:
            continue
        property_payload = serialize_property_listing(
            db,
            match[0],
            submitter=match[1],
            favorite_id=favorite.id,
            user_id=context.user_id,
        )
        items.append(
            {
                "id": str(favorite.id),
                "user_id": str(favorite.user_id),
                "property_hash": int(property_payload["property_hash"]),
                "property": property_payload,
            }
        )
    pagination = pagination_meta(total, page, pageSize)
    return success_response({**pagination, "items": items}, meta={"pagination": pagination})


@router.post("")
def add_favorite(payload: FavoriteCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    property_id = resolve_property_uuid_or_404(db, payload.property_hash)
    existing = db.execute(
        select(UserPropertyFavorite).where(
            UserPropertyFavorite.user_id == context.user_id,
            UserPropertyFavorite.property_id == property_id,
        )
    ).scalars().first()
    if existing:
        favorite = existing
    else:
        favorite = UserPropertyFavorite(
            id=uuid4(),
            user_id=context.user_id,
            property_id=property_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(favorite)
        db.flush()
    match = get_public_submission_or_404(db, property_id)
    property_payload = serialize_property_listing(
        db,
        match[0],
        submitter=match[1],
        favorite_id=favorite.id,
        user_id=context.user_id,
    )
    db.commit()
    return success_response(
        {
            "id": str(favorite.id),
            "user_id": str(context.user_id),
            "property_hash": int(property_payload["property_hash"]),
            "property": property_payload,
        },
        "Favorite added successfully",
    )


@router.delete("/{property_hash}")
def remove_favorite(property_hash: str, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    lookup = favorite_lookup(db, context.user_id)
    property_id = None
    resolved_property_id = None
    try:
        resolved_property_id = resolve_property_uuid_or_404(db, property_hash)
    except HTTPException:
        resolved_property_id = None

    for candidate_property_id, favorite in lookup.items():
        if str(candidate_property_id) == property_hash or str(favorite.id) == property_hash:
            property_id = candidate_property_id
            break
        if resolved_property_id and resolved_property_id == candidate_property_id:
            property_id = candidate_property_id
            break
    if property_id is None:
        if resolved_property_id is None:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Favorite not found")
        property_id = resolved_property_id

    db.execute(
        delete(UserPropertyFavorite).where(
            UserPropertyFavorite.user_id == context.user_id,
            UserPropertyFavorite.property_id == property_id,
        )
    )
    db.commit()
    return success_response(True, "Favorite removed successfully")
