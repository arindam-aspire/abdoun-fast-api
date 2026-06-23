from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.models.live_schema import Notification, NotificationPreference
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_NOT_FOUND

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def serialize_notification(notification: Notification) -> dict:
    return {
        "id": str(notification.id),
        "typeKey": notification.type_key,
        "eventType": notification.event_type or notification.type_key,
        "title": notification.title,
        "message": notification.message,
        "actionUrl": notification.action_url,
        "isRead": bool(notification.is_read),
        "createdAt": iso(notification.created_at),
        "readAt": iso(notification.read_at),
        "archivedAt": iso(notification.archived_at),
        "data": notification.data,
    }


def get_notification_or_404(db: DBSessionDep, notification_id: UUID, user_id: UUID) -> Notification:
    notification = db.get(Notification, notification_id)
    if not notification or notification.recipient_user_id != user_id:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Notification not found")
    return notification


@router.get("")
def list_notifications(
    context: AuthenticatedContext,
    db: DBSessionDep,
    page: int = 1,
    pageSize: int = 10,
    includeArchived: bool = False,
) -> dict:
    page = max(page, 1)
    pageSize = max(min(pageSize, 100), 1)
    stmt = (
        select(Notification)
        .where(Notification.recipient_user_id == context.user_id)
        .order_by(Notification.created_at.desc())
    )
    if not includeArchived:
        stmt = stmt.where(Notification.archived_at.is_(None))
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    meta = pagination(total, page, pageSize)
    return success_response({**meta, "items": [serialize_notification(row) for row in rows]}, meta={"pagination": meta})


@router.get("/unread-count")
def unread_count(context: AuthenticatedContext, db: DBSessionDep) -> dict:
    count = db.execute(
        select(func.count()).where(
            Notification.recipient_user_id == context.user_id,
            Notification.is_read.is_(False),
            Notification.archived_at.is_(None),
        )
    ).scalar() or 0
    return success_response({"unreadCount": count})


@router.put("/read-all")
def mark_all_read(context: AuthenticatedContext, db: DBSessionDep) -> dict:
    notifications = db.execute(
        select(Notification).where(
            Notification.recipient_user_id == context.user_id,
            Notification.is_read.is_(False),
            Notification.archived_at.is_(None),
        )
    ).scalars().all()
    now = utc_now()
    for notification in notifications:
        notification.is_read = True
        notification.read_at = now
    db.commit()
    return success_response({"updated": len(notifications)}, "Notifications marked as read")


@router.get("/preferences")
def list_notification_preferences(context: AuthenticatedContext, db: DBSessionDep) -> dict:
    rows = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.user_id == context.user_id)
        .order_by(NotificationPreference.notification_type.asc())
    ).scalars().all()
    return success_response(
        {
            "items": [
                {
                    "id": str(row.id),
                    "notification_type": row.notification_type,
                    "enabled": bool(row.enabled),
                    "created_at": iso(row.created_at),
                    "updated_at": iso(row.updated_at),
                }
                for row in rows
            ]
        }
    )


@router.put("/{notification_id}/read")
def mark_read(notification_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    notification = get_notification_or_404(db, notification_id, context.user_id)
    notification.is_read = True
    notification.read_at = notification.read_at or utc_now()
    db.commit()
    db.refresh(notification)
    return success_response(serialize_notification(notification), "Notification marked as read")


@router.post("/{notification_id}/archive")
def archive_notification(notification_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    notification = get_notification_or_404(db, notification_id, context.user_id)
    notification.archived_at = notification.archived_at or utc_now()
    db.commit()
    return success_response(True, "Notification archived")


@router.post("/{notification_id}/unarchive")
def unarchive_notification(notification_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    notification = get_notification_or_404(db, notification_id, context.user_id)
    notification.archived_at = None
    db.commit()
    return success_response(True, "Notification unarchived")


@router.delete("/{notification_id}")
def delete_notification(notification_id: UUID, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    notification = get_notification_or_404(db, notification_id, context.user_id)
    db.execute(delete(Notification).where(Notification.id == notification.id))
    db.commit()
    return success_response({"id": str(notification_id)}, "Notification deleted")
