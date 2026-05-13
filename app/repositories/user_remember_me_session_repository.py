"""Persistence for Remember Me sessions (hashed opaque token + encrypted Cognito refresh)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.user_remember_me_session import UserRememberMeSession


class UserRememberMeSessionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_active_by_token_hash(self, token_hash: str) -> Optional[UserRememberMeSession]:
        now = datetime.now(timezone.utc)
        stmt = select(UserRememberMeSession).where(
            UserRememberMeSession.token_hash == token_hash,
            UserRememberMeSession.revoked_at.is_(None),
            UserRememberMeSession.expires_at > now,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        cognito_refresh_encrypted: str,
        cognito_username: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> UserRememberMeSession:
        row = UserRememberMeSession(
            user_id=user_id,
            token_hash=token_hash,
            cognito_refresh_encrypted=cognito_refresh_encrypted,
            cognito_username=cognito_username,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def update_after_rotation(
        self,
        session_id: uuid.UUID,
        *,
        new_token_hash: str,
        cognito_refresh_encrypted: str,
        cognito_username: str,
        expires_at: datetime,
        last_used_at: datetime,
    ) -> None:
        stmt = (
            update(UserRememberMeSession)
            .where(UserRememberMeSession.id == session_id)
            .values(
                token_hash=new_token_hash,
                cognito_refresh_encrypted=cognito_refresh_encrypted,
                cognito_username=cognito_username,
                expires_at=expires_at,
                last_used_at=last_used_at,
            )
        )
        self._db.execute(stmt)

    def touch_last_used(self, session_id: uuid.UUID, *, last_used_at: datetime) -> None:
        stmt = (
            update(UserRememberMeSession)
            .where(UserRememberMeSession.id == session_id)
            .values(last_used_at=last_used_at)
        )
        self._db.execute(stmt)

    def revoke_by_id(self, session_id: uuid.UUID, *, revoked_at: datetime) -> None:
        stmt = (
            update(UserRememberMeSession)
            .where(UserRememberMeSession.id == session_id)
            .values(revoked_at=revoked_at)
        )
        self._db.execute(stmt)

    def revoke_all_for_user(self, user_id: uuid.UUID, *, revoked_at: datetime) -> None:
        stmt = (
            update(UserRememberMeSession)
            .where(
                UserRememberMeSession.user_id == user_id,
                UserRememberMeSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        self._db.execute(stmt)
