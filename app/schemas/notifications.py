"""Pydantic schemas for in-app notifications (Phase 1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class NotificationResponse(BaseModel):
    id: uuid.UUID
    type_key: str = Field(alias="typeKey")
    title: str
    message: str
    is_read: bool = Field(alias="isRead")
    created_at: datetime = Field(alias="createdAt")
    read_at: Optional[datetime] = Field(default=None, alias="readAt")
    archived_at: Optional[datetime] = Field(default=None, alias="archivedAt")
    data: Optional[Dict[str, Any]] = None

    model_config = {"populate_by_name": True}


class NotificationsListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool


class UnreadCountResponse(BaseModel):
    unreadCount: int


class MarkAllReadResponse(BaseModel):
    updated: int


class NotificationBulkDeleteRequest(BaseModel):
    notification_ids: List[uuid.UUID] = Field(alias="notificationIds", min_length=1, max_length=500)

    model_config = {"populate_by_name": True}

    @field_validator("notification_ids")
    @classmethod
    def _ensure_unique_ids(cls, v: List[uuid.UUID]) -> List[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("Duplicate notification IDs are not allowed")
        return v


class NotificationBulkDeleteResponse(BaseModel):
    deleted_count: int = Field(alias="deletedCount")
    failed_ids: List[uuid.UUID] = Field(alias="failedIds")

    model_config = {"populate_by_name": True}


class NotificationBulkActionResponse(BaseModel):
    affected_count: int = Field(alias="affectedCount")
    failed_ids: List[uuid.UUID] = Field(alias="failedIds")

    model_config = {"populate_by_name": True}

