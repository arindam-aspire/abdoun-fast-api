"""Notification preference service (Phase 1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable, Sequence

from fastapi import HTTPException

from app.constants.notification_types import NON_DISABLEABLE_TYPES
from app.repositories.notification_preferences_repository import NotificationPreferencesRepository
from app.utils.status_codes import HTTPStatus


@dataclass(frozen=True, slots=True)
class PreferenceItem:
    notification_type: str
    enabled: bool


class NotificationPreferenceService:
    def __init__(self, repo: NotificationPreferencesRepository) -> None:
        self._repo = repo

    def list_preferences(self, *, user_id: uuid.UUID) -> Sequence[PreferenceItem]:
        rows = self._repo.list_for_user(user_id=user_id)
        return [PreferenceItem(notification_type=r.notification_type, enabled=bool(r.enabled)) for r in rows]

    def is_enabled(self, *, user_id: uuid.UUID, notification_type: str) -> bool:
        row = self._repo.get_by_user_and_type(user_id=user_id, notification_type=notification_type)
        if row is None:
            return True  # default enabled in Phase 1
        return bool(row.enabled)

    def update_preferences(self, *, user_id: uuid.UUID, items: Iterable[PreferenceItem]) -> Sequence[PreferenceItem]:
        # Enforce Phase 1 rules: system notifications cannot be disabled.
        for it in items:
            if it.notification_type in NON_DISABLEABLE_TYPES and not it.enabled:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Notification type '{it.notification_type}' cannot be disabled.",
                )

        out: list[PreferenceItem] = []
        for it in items:
            row = self._repo.upsert(
                user_id=user_id,
                notification_type=it.notification_type,
                enabled=it.enabled,
            )
            out.append(PreferenceItem(notification_type=row.notification_type, enabled=bool(row.enabled)))

        self._repo.commit()
        return out

