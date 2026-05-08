import uuid

import pytest
from fastapi import HTTPException

from app.models.notification import Notification
from app.models.user import User
from app.services.notification_service import NotificationService


class _FakeRepo:
    def __init__(self, notif: Notification | None) -> None:
        self._notif = notif

    def get_by_id(self, _id):
        return self._notif

    def mark_as_read(self, *, notification_id, read_at):
        return True

    def archive(self, *, notification_id, archived_at):
        return True

    def archive_many(self, *, notification_ids, archived_at):
        return len(notification_ids)

    def mark_all_as_read(self, *, user_id, read_at):
        return 1

    def unread_count(self, *, user_id):
        return 0

    def list_for_user(self, *, user_id, limit, offset, include_archived):
        return ([], 0)

    def list_by_ids(self, *, notification_ids):
        return [self._notif] if self._notif is not None else []

    def create(self, *, notification):
        return notification

    def commit(self):
        return None

    def refresh(self, _):
        return None

    def rollback(self):
        return None

    def now_utc(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


class _FakePrefs:
    def is_enabled(self, *, user_id, notification_type):
        return True


class _FakeTemplates:
    def build(self, *, type_key, data=None):
        return ("t", "m")


def _user(user_id: uuid.UUID) -> User:
    u = User(full_name="x", email=f"{user_id}@x.test", is_active=True)
    u.id = user_id  # type: ignore[attr-defined]
    return u


def test_mark_read_forbidden_when_not_owner() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    notif = Notification(
        recipient_user_id=owner_id,
        actor_user_id=None,
        type_key="x",
        title="t",
        message="m",
        data=None,
        is_read=False,
    )
    notif.id = uuid.uuid4()  # type: ignore[attr-defined]
    svc = NotificationService(_FakeRepo(notif), _FakePrefs(), _FakeTemplates())
    with pytest.raises(HTTPException) as e:
        svc.mark_as_read(current_user=_user(other_id), notification_id=notif.id)
    assert e.value.status_code == 403


def test_archive_forbidden_when_not_owner() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    notif = Notification(
        recipient_user_id=owner_id,
        actor_user_id=None,
        type_key="x",
        title="t",
        message="m",
        data=None,
        is_read=False,
    )
    notif.id = uuid.uuid4()  # type: ignore[attr-defined]
    svc = NotificationService(_FakeRepo(notif), _FakePrefs(), _FakeTemplates())
    with pytest.raises(HTTPException) as e:
        svc.archive(current_user=_user(other_id), notification_id=notif.id)
    assert e.value.status_code == 403


def test_unarchive_forbidden_when_not_owner() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    notif = Notification(
        recipient_user_id=owner_id,
        actor_user_id=None,
        type_key="x",
        title="t",
        message="m",
        data=None,
        is_read=False,
    )
    notif.id = uuid.uuid4()  # type: ignore[attr-defined]
    from datetime import datetime, timezone
    notif.archived_at = datetime.now(timezone.utc)
    svc = NotificationService(_FakeRepo(notif), _FakePrefs(), _FakeTemplates())
    with pytest.raises(HTTPException) as e:
        svc.unarchive(current_user=_user(other_id), notification_id=notif.id)
    assert e.value.status_code == 403


def test_delete_forbidden_when_not_owner() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    notif = Notification(
        recipient_user_id=owner_id,
        actor_user_id=None,
        type_key="x",
        title="t",
        message="m",
        data=None,
        is_read=False,
    )
    notif.id = uuid.uuid4()  # type: ignore[attr-defined]
    svc = NotificationService(_FakeRepo(notif), _FakePrefs(), _FakeTemplates())
    with pytest.raises(HTTPException) as e:
        svc.delete(current_user=_user(other_id), notification_id=notif.id)
    assert e.value.status_code == 403

