"""Pydantic schemas for notification settings/preferences (Phase 1)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class NotificationPreferenceItem(BaseModel):
    notification_type: str = Field(alias="notificationType")
    enabled: bool

    model_config = {"populate_by_name": True}


class NotificationSettingsResponse(BaseModel):
    items: List[NotificationPreferenceItem]


class NotificationSettingsUpdateRequest(BaseModel):
    items: List[NotificationPreferenceItem]

