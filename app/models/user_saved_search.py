"""User saved searches ORM model."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.property import Base


class UserSavedSearch(Base):
    """Stores reusable user-defined search criteria and notification preferences."""

    __tablename__ = "user_saved_searches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(search_criteria) = 'object'",
            name="ck_user_saved_searches_search_criteria_object",
        ),
    )

