import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.deps.notifications import get_notification_service, get_notification_preference_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User


class _FakeNotificationService:
    def list_notifications(self, *, current_user, page, page_size, include_archived):
        return ([], 0)

    def unread_count(self, *, current_user):
        return 0

    def mark_as_read(self, *, current_user, notification_id):
        return True

    def mark_all_as_read(self, *, current_user):
        return 0

    def archive(self, *, current_user, notification_id):
        return True

    def unarchive(self, *, current_user, notification_id):
        return True

    def delete(self, *, current_user, notification_id):
        return True

    def bulk_delete(self, *, current_user, notification_ids):
        return (len(notification_ids), [])

    def bulk_archive(self, *, current_user, notification_ids):
        return (len(notification_ids), [])

    def bulk_unarchive(self, *, current_user, notification_ids):
        return (len(notification_ids), [])


class _FakePreferenceService:
    def list_preferences(self, *, user_id):
        return []

    def update_preferences(self, *, user_id, items):
        return items


def _fake_user() -> User:
    u = User(full_name="Test", email="test@example.com", is_active=True)
    u.id = uuid.UUID("00000000-0000-0000-0000-000000000001")  # type: ignore[attr-defined]
    return u


def test_notifications_endpoints_require_auth_override() -> None:
    # Override auth + services for route smoke tests.
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_notification_service] = lambda: _FakeNotificationService()
    app.dependency_overrides[get_notification_preference_service] = lambda: _FakePreferenceService()
    try:
        client = TestClient(app)
        assert client.get("/api/v1/notifications").status_code == 200
        assert client.get("/api/v1/notifications/unread-count").status_code == 200
        nid = str(uuid.uuid4())
        assert client.put(f"/api/v1/notifications/{nid}/read").status_code == 200
        assert client.put("/api/v1/notifications/read-all").status_code == 200
        assert client.post(f"/api/v1/notifications/{nid}/archive").status_code == 200
        assert client.post(f"/api/v1/notifications/{nid}/unarchive").status_code == 200
        assert client.post(
            "/api/v1/notifications/bulk-archive",
            json={"notificationIds": [str(uuid.uuid4()), str(uuid.uuid4())]},
        ).status_code == 200
        assert client.post(
            "/api/v1/notifications/bulk-unarchive",
            json={"notificationIds": [str(uuid.uuid4()), str(uuid.uuid4())]},
        ).status_code == 200
        assert client.delete(f"/api/v1/notifications/{nid}").status_code == 200
        assert client.post(
            "/api/v1/notifications/bulk-delete",
            json={"notificationIds": [str(uuid.uuid4()), str(uuid.uuid4())]},
        ).status_code == 200
        assert client.get("/api/v1/notification-settings").status_code == 200
        assert client.put("/api/v1/notification-settings", json={"items": []}).status_code == 200
    finally:
        app.dependency_overrides.clear()

