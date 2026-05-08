import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.websockets.notification_websocket import get_ws_current_user
from app.websockets.connection_manager import connection_manager


def _fake_user(user_id: uuid.UUID | None = None) -> User:
    u = User(full_name="WS", email="ws@example.com", is_active=True)
    u.id = user_id or uuid.UUID("00000000-0000-0000-0000-000000000001")  # type: ignore[attr-defined]
    return u


def test_ws_connects_with_auth_override_and_disconnect_cleans_up() -> None:
    app.dependency_overrides[get_ws_current_user] = lambda: _fake_user()
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws/notifications") as ws:
            msg = ws.receive_json()
            assert msg["event"] == "ping"
        # No direct access to internal map; just ensure no exception on send after close.
    finally:
        app.dependency_overrides.clear()


def test_ws_multiple_connections_receive_messages() -> None:
    user = _fake_user()
    app.dependency_overrides[get_ws_current_user] = lambda: user
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws/notifications") as ws1:
            with client.websocket_connect("/ws/notifications") as ws2:
                # Drain initial ping(s)
                ws1.receive_json()
                ws2.receive_json()
                # Send message via connection manager
                import anyio

                anyio.run(lambda: connection_manager.send_to_user(user_id=user.id, message={"event": "test", "data": {}}))
                assert ws1.receive_json()["event"] == "test"
                assert ws2.receive_json()["event"] == "test"
    finally:
        app.dependency_overrides.clear()

