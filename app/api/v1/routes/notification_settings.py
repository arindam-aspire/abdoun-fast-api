"""Notification settings APIs (Phase 1: in-app preferences)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.notifications import get_notification_preference_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User
from app.schemas.notification_settings import (
    NotificationPreferenceItem,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
)
from app.services.notification_preference_service import NotificationPreferenceService, PreferenceItem
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus


router = APIRouter()


@router.get(
    "",
    response_model=StandardResponse[NotificationSettingsResponse],
    status_code=HTTPStatus.OK,
)
def get_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationPreferenceService, Depends(get_notification_preference_service)],
) -> StandardResponse[NotificationSettingsResponse]:
    items = service.list_preferences(user_id=current_user.id)
    body = NotificationSettingsResponse(
        items=[
            NotificationPreferenceItem(notificationType=i.notification_type, enabled=i.enabled)
            for i in items
        ]
    )
    return create_success_response(data=body, message=None)


@router.put(
    "",
    response_model=StandardResponse[NotificationSettingsResponse],
    status_code=HTTPStatus.OK,
)
def update_settings(
    payload: NotificationSettingsUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationPreferenceService, Depends(get_notification_preference_service)],
) -> StandardResponse[NotificationSettingsResponse]:
    updated = service.update_preferences(
        user_id=current_user.id,
        items=[
            PreferenceItem(notification_type=i.notification_type, enabled=i.enabled)
            for i in payload.items
        ],
    )
    body = NotificationSettingsResponse(
        items=[
            NotificationPreferenceItem(notificationType=i.notification_type, enabled=i.enabled)
            for i in updated
        ]
    )
    return create_success_response(data=body, message=None)

