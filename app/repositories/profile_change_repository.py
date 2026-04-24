"""Persistence for user profile change OTP challenges (email/phone)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.user_profile_change_challenge import UserProfileChangeChallenge


class ProfileChangeRepository:
    """CRUD for `UserProfileChangeChallenge` rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def delete_for_user_purpose(self, *, user_id: uuid.UUID, purpose: str) -> None:
        """Remove any existing challenges for this user and purpose."""
        self._db.execute(
            delete(UserProfileChangeChallenge).where(
                UserProfileChangeChallenge.user_id == user_id,
                UserProfileChangeChallenge.purpose == purpose,
            )
        )

    def create_challenge(
        self,
        *,
        user_id: uuid.UUID,
        purpose: str,
        new_value: str,
        otp_hash: str,
        expires_at: datetime,
        cognito_custom_auth_session: Optional[str] = None,
    ) -> UserProfileChangeChallenge:
        """Insert a new challenge (caller should delete old rows for purpose first)."""
        row = UserProfileChangeChallenge(
            user_id=user_id,
            purpose=purpose,
            new_value=new_value,
            otp_hash=otp_hash,
            expires_at=expires_at,
            cognito_custom_auth_session=cognito_custom_auth_session,
        )
        self._db.add(row)
        return row

    def get_valid_challenge(
        self,
        *,
        user_id: uuid.UUID,
        purpose: str,
        new_value: str,
    ) -> Optional[UserProfileChangeChallenge]:
        """Return the latest non-expired challenge matching user, purpose, and target value."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(UserProfileChangeChallenge)
            .where(
                UserProfileChangeChallenge.user_id == user_id,
                UserProfileChangeChallenge.purpose == purpose,
                UserProfileChangeChallenge.new_value == new_value,
                UserProfileChangeChallenge.expires_at > now,
            )
            .order_by(UserProfileChangeChallenge.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def delete_challenge(self, challenge: UserProfileChangeChallenge) -> None:
        """Remove a challenge after successful verification."""
        self._db.delete(challenge)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)
