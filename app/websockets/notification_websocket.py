"""WebSocket endpoint for realtime in-app notifications (single-instance)."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

import anyio
from fastapi import APIRouter, Depends, Query, WebSocket
from fastapi.websockets import WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_from_token
from app.db.session import get_db
from app.models.user import User
from app.websockets.connection_manager import connection_manager


router = APIRouter()


async def get_ws_current_user(
    websocket: WebSocket,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[Optional[str], Query()] = None,
) -> User:
    """Authenticate websocket connection with JWT.

    Supports:
    - token query parameter
    - Authorization: Bearer <token>
    """
    jwt = (token or "").strip()
    if not jwt:
        auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            jwt = auth.split(" ", 1)[1].strip()
    return await get_current_user_from_token(token=jwt, db=db)


@router.websocket("/ws/notifications")
async def notifications_ws(
    websocket: WebSocket,
    current_user: Annotated[User, Depends(get_ws_current_user)],
) -> None:
    # Validate user before accepting.
    await websocket.accept()

    user_id: uuid.UUID = current_user.id
    await connection_manager.connect(user_id=user_id, websocket=websocket)

    try:
        try:
            await websocket.send_json({"event": "ping", "data": {}})
        except Exception:
            return

        # Lightweight keepalive loop:
        # - periodically send ping
        # - read any inbound messages (pong/keepalive) without blocking forever
        while True:
            try:
                with anyio.fail_after(30):
                    await websocket.receive_text()
            except TimeoutError:
                # No client message; keep connection alive.
                try:
                    await websocket.send_json({"event": "ping", "data": {}})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(user_id=user_id, websocket=websocket)

