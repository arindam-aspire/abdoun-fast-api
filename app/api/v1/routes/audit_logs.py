from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.models.live_schema import ActivityLog
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_FORBIDDEN

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def iso(value) -> str | None:
    return value.isoformat() if value else None


def pagination(total: int, page: int, page_size: int) -> dict:
    total_pages = math.ceil(total / page_size) if total else 1
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }


def serialize_activity(row: ActivityLog) -> dict:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id) if row.user_id else None,
        "property_id": str(row.property_id) if row.property_id else None,
        "activity_type": row.activity_type,
        "message": row.message,
        "tone": row.tone,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


@router.get("")
def list_audit_logs(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 25,
    activityType: str | None = None,
) -> dict:
    role_names = {role.lower() for role in context.roles}
    if "admin" not in role_names and "super_admin" not in role_names:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")
    page = max(page, 1)
    pageSize = max(min(pageSize, 100), 1)
    stmt = select(ActivityLog).order_by(ActivityLog.created_at.desc())
    if activityType:
        stmt = stmt.where(ActivityLog.activity_type == activityType)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    meta = pagination(total, page, pageSize)
    return success_response({**meta, "items": [serialize_activity(row) for row in rows]}, meta={"pagination": meta})

