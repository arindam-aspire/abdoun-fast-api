import uuid

import pytest
from fastapi import HTTPException

from app.constants.notification_types import NotificationType
from app.services.notification_preference_service import NotificationPreferenceService, PreferenceItem


class _FakeRepo:
    def __init__(self) -> None:
        self.rows = {}
        self.committed = False

    def list_for_user(self, *, user_id):
        return []

    def get_by_user_and_type(self, *, user_id, notification_type):
        return None

    def upsert(self, *, user_id, notification_type, enabled):
        self.rows[(user_id, notification_type)] = enabled
        return type("Row", (), {"notification_type": notification_type, "enabled": enabled})

    def commit(self):
        self.committed = True


def test_system_announcement_cannot_be_disabled() -> None:
    svc = NotificationPreferenceService(_FakeRepo())
    with pytest.raises(HTTPException):
        svc.update_preferences(
            user_id=uuid.uuid4(),
            items=[PreferenceItem(notification_type=NotificationType.SYSTEM_ANNOUNCEMENT.value, enabled=False)],
        )


def test_update_preferences_commits() -> None:
    repo = _FakeRepo()
    svc = NotificationPreferenceService(repo)
    user_id = uuid.uuid4()
    svc.update_preferences(
        user_id=user_id,
        items=[PreferenceItem(notification_type=NotificationType.LEAD_CREATED.value, enabled=False)],
    )
    assert repo.committed is True

