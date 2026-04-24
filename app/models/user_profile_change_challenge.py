"""Pending OTP challenges for self-service email/phone profile updates."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.property import Base
from app.models.user import FK_USERS_ID


class UserProfileChangeChallenge(Base):
    """Pending profile change: phone uses app-hashed OTP; email uses Cognito CUSTOM_AUTH session.

    Email delivery matches ``POST /auth/login/otp/request`` (Lambda + SES/SMS to the user's current pool
    attributes). The intended new email is stored in ``new_value`` until verify succeeds.
    """

    __tablename__ = "user_profile_change_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    new_value: Mapped[str] = mapped_column(String(255), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    cognito_custom_auth_session: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
