from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.models.live_schema import UserSavedSearch
from app.schemas.saved_searches import SavedSearchCreate, SavedSearchUpdate
from app.services.public_properties import iso, pagination_meta, utc_now
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_NOT_FOUND

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def serialize_saved_search(record: UserSavedSearch) -> dict:
    criteria = record.search_criteria or {}
    return {
        "id": str(record.id),
        "name": record.name,
        "search_criteria": criteria,
        "query_string": urlencode({key: value for key, value in criteria.items() if value not in (None, "")}),
        "notification_enabled": record.notification_enabled,
        "last_run_at": iso(record.last_run_at),
    }


def get_saved_search_or_404(db: DBSessionDep, search_id: UUID, user_id: UUID) -> UserSavedSearch:
    record = db.get(UserSavedSearch, search_id)
    if not record or record.user_id != user_id:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Saved search not found")
    return record


@router.post("")
def create_saved_search(payload: SavedSearchCreate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    record = UserSavedSearch(
        user_id=context.user_id,
        name=payload.name.strip(),
        search_criteria=payload.search_criteria,
        notification_enabled=payload.notification_enabled,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return success_response(serialize_saved_search(record), "Saved search created successfully")


@router.get("")
def list_saved_searches(context: AuthenticatedContext, db: DBSessionDep, page: int = 1, pageSize: int = 10) -> dict:
    page = max(page, 1)
    pageSize = max(min(pageSize, 100), 1)
    stmt = (
        select(UserSavedSearch)
        .where(UserSavedSearch.user_id == context.user_id)
        .order_by(UserSavedSearch.updated_at.desc())
    )
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    records = db.execute(stmt.offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    pagination = pagination_meta(total, page, pageSize)
    return success_response({**pagination, "items": [serialize_saved_search(record) for record in records]}, meta={"pagination": pagination})


@router.get("/{search_id}")
def get_saved_search(search_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    return success_response(serialize_saved_search(get_saved_search_or_404(db, search_id, context.user_id)))


@router.patch("/{search_id}")
def update_saved_search(search_id: UUID, payload: SavedSearchUpdate, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    record = get_saved_search_or_404(db, search_id, context.user_id)
    record.name = payload.name.strip()
    record.search_criteria = payload.search_criteria
    record.updated_at = utc_now()
    db.commit()
    db.refresh(record)
    return success_response(serialize_saved_search(record), "Saved search updated successfully")


@router.delete("/{search_id}")
def delete_saved_search(search_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    get_saved_search_or_404(db, search_id, context.user_id)
    db.execute(delete(UserSavedSearch).where(UserSavedSearch.id == search_id, UserSavedSearch.user_id == context.user_id))
    db.commit()
    return success_response(True, "Saved search deleted successfully")

