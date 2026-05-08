import uuid

from app.models.notification import Notification
from app.services.realtime_notification_service import RealtimeNotificationService


class _FakeManager:
    def __init__(self) -> None:
        self.calls = []

    async def send_to_user(self, *, user_id, message):
        self.calls.append((user_id, message))


def test_realtime_payload_shape_smoke() -> None:
    manager = _FakeManager()
    svc = RealtimeNotificationService(manager)
    n = Notification(
        recipient_user_id=uuid.uuid4(),
        actor_user_id=None,
        type_key="favorite.added",
        title="Property Added to Favorites",
        message="Property #1 has been added to your favorites.",
        data={"property_hash": 1},
        is_read=False,
    )
    n.id = uuid.uuid4()  # type: ignore[attr-defined]
    # Should not raise (best-effort call path).
    svc.notification_created(notification=n, unread_count=1)

