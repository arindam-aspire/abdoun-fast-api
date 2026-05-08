"""WebSocket connection manager (single-instance, in-memory).

Phase: realtime in-app notifications (no Redis / no multi-node sync).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, DefaultDict, Set

import anyio
from fastapi import WebSocket


class ConnectionManager:
    """Tracks active WebSocket connections per user_id."""

    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._connections: DefaultDict[uuid.UUID, Set[WebSocket]] = defaultdict(set)

    async def connect(self, *, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, *, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(user_id, None)

    async def send_to_user(self, *, user_id: uuid.UUID, message: dict[str, Any]) -> None:
        """Send JSON message to all active connections of user_id.

        Disconnected/broken sockets are ignored and cleaned up.
        """
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))

        if not sockets:
            return

        stale: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                conns = self._connections.get(user_id)
                if conns:
                    for ws in stale:
                        conns.discard(ws)
                    if not conns:
                        self._connections.pop(user_id, None)


# Single-process singleton (required to share state between routes/services in one instance).
connection_manager = ConnectionManager()

