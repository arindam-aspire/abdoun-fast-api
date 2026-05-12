import uuid

from app.models.notification import Notification
from app.services.realtime_notification_service import RealtimeNotificationService, _notification_payload


class _FakeManager:
    def __init__(self) -> None:
        self.calls = []

    async def send_to_user(self, *, user_id, message):
        self.calls.append((user_id, message))


def test_notification_payload_matches_api_contract() -> None:
    n = Notification(
        recipient_user_id=uuid.uuid4(),
        actor_user_id=None,
        type_key="lead.created",
        event_type="lead.created",
        idempotency_key=None,
        action_url="/agent-dashboard/leads-and-inquiries",
        title="New Lead Created",
        message="msg",
        data={"metadata": {"k": "v"}},
        is_read=False,
    )
    n.id = uuid.uuid4()  # type: ignore[attr-defined]
    data = _notification_payload(notification=n, unread_count=3)
    assert data["id"] == str(n.id)
    assert data["event_type"] == "lead.created"
    assert data["type_key"] == "lead.created"
    assert data["action_url"] == "/agent-dashboard/leads-and-inquiries"
    assert data["metadata"] == {"k": "v"}
    assert data["unread_count"] == 3


def test_realtime_notification_created_does_not_raise() -> None:
    manager = _FakeManager()
    svc = RealtimeNotificationService(manager)
    n = Notification(
        recipient_user_id=uuid.uuid4(),
        actor_user_id=None,
        type_key="lead.created",
        event_type="lead.created",
        idempotency_key=None,
        action_url="/x",
        title="t",
        message="m",
        data=None,
        is_read=False,
    )
    n.id = uuid.uuid4()  # type: ignore[attr-defined]
    svc.notification_created(notification=n, unread_count=1)
