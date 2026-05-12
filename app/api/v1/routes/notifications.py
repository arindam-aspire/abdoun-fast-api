"""Notification center APIs (Phase 1: in-app only, polling-based)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.notifications import get_notification_service
from app.api.v1.deps.security import get_current_user
from app.domains.shared.pagination import PageParams, calculate_pagination
from app.models.user import User
from app.schemas.notifications import (
    MarkAllReadResponse,
    NotificationBulkActionResponse,
    NotificationBulkDeleteRequest,
    NotificationBulkDeleteResponse,
    NotificationResponse,
    NotificationsListResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus


router = APIRouter()


@router.get(
    "",
    response_model=StandardResponse[NotificationsListResponse],
    status_code=HTTPStatus.OK,
)
def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    params: Annotated[PageParams, Depends()],
    include_archived: Annotated[bool, Query(alias="includeArchived")] = False,
) -> StandardResponse[NotificationsListResponse]:
    items, total = service.list_notifications(
        current_user=current_user,
        page=params.page,
        page_size=params.page_size,
        include_archived=include_archived,
    )
    meta = calculate_pagination(page=params.page, page_size=params.page_size, total=total)
    body = NotificationsListResponse(
        items=[
            NotificationResponse(
                id=n.id,
                typeKey=n.type_key,
                eventType=n.event_type or n.type_key,
                title=n.title,
                message=n.message,
                actionUrl=n.action_url
                or (n.data.get("action_url") if isinstance(n.data, dict) else None),
                isRead=n.is_read,
                createdAt=n.created_at,
                readAt=n.read_at,
                archivedAt=n.archived_at,
                data=n.data,
            )
            for n in items
        ],
        total=total,
        page=meta.page,
        pageSize=meta.page_size,
        totalPages=meta.total_pages,
        hasNext=meta.has_next,
        hasPrevious=meta.has_previous,
    )
    return create_success_response(data=body, message=None, pagination=meta)


@router.get(
    "/unread-count",
    response_model=StandardResponse[UnreadCountResponse],
    status_code=HTTPStatus.OK,
)
def unread_count(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[UnreadCountResponse]:
    cnt = service.unread_count(current_user=current_user)
    return create_success_response(data=UnreadCountResponse(unreadCount=cnt), message=None)


@router.put(
    "/{notification_id}/read",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def mark_read(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[bool]:
    updated = service.mark_as_read(current_user=current_user, notification_id=notification_id)
    return create_success_response(data=updated, message=None)


@router.put(
    "/read-all",
    response_model=StandardResponse[MarkAllReadResponse],
    status_code=HTTPStatus.OK,
)
def mark_all_read(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[MarkAllReadResponse]:
    updated = service.mark_all_as_read(current_user=current_user)
    return create_success_response(data=MarkAllReadResponse(updated=updated), message=None)


@router.post(
    "/{notification_id}/archive",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def archive_notification(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[bool]:
    archived = service.archive(current_user=current_user, notification_id=notification_id)
    return create_success_response(data=archived, message="Notification archived successfully")


@router.post(
    "/{notification_id}/unarchive",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def unarchive_notification(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[bool]:
    unarchived = service.unarchive(current_user=current_user, notification_id=notification_id)
    return create_success_response(data=unarchived, message="Notification unarchived successfully")


@router.post(
    "/bulk-archive",
    response_model=StandardResponse[NotificationBulkActionResponse],
    status_code=HTTPStatus.OK,
)
def bulk_archive_notifications(
    payload: NotificationBulkDeleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[NotificationBulkActionResponse]:
    affected_count, failed_ids = service.bulk_archive(
        current_user=current_user,
        notification_ids=payload.notification_ids,
    )
    return create_success_response(
        data=NotificationBulkActionResponse(
            affectedCount=affected_count,
            failedIds=failed_ids,
        ),
        message="Notifications archived successfully",
    )


@router.post(
    "/bulk-unarchive",
    response_model=StandardResponse[NotificationBulkActionResponse],
    status_code=HTTPStatus.OK,
)
def bulk_unarchive_notifications(
    payload: NotificationBulkDeleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[NotificationBulkActionResponse]:
    affected_count, failed_ids = service.bulk_unarchive(
        current_user=current_user,
        notification_ids=payload.notification_ids,
    )
    return create_success_response(
        data=NotificationBulkActionResponse(
            affectedCount=affected_count,
            failedIds=failed_ids,
        ),
        message="Notifications unarchived successfully",
    )


@router.delete(
    "/{notification_id}",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def delete_notification(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[bool]:
    deleted = service.delete(current_user=current_user, notification_id=notification_id)
    return create_success_response(data=deleted, message="Notification deleted successfully")


@router.post(
    "/bulk-delete",
    response_model=StandardResponse[NotificationBulkDeleteResponse],
    status_code=HTTPStatus.OK,
)
def bulk_delete_notifications(
    payload: NotificationBulkDeleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StandardResponse[NotificationBulkDeleteResponse]:
    deleted_count, failed_ids = service.bulk_delete(
        current_user=current_user,
        notification_ids=payload.notification_ids,
    )
    return create_success_response(
        data=NotificationBulkDeleteResponse(
            deletedCount=deleted_count,
            failedIds=failed_ids,
        ),
        message="Notifications deleted successfully",
    )

