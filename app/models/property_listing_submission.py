"""Property listing submission workflow ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.property import Base

FK_USERS_ID = "users.id"
FK_PROPERTIES_NORMALIZED_ID = "properties_normalized.id"


class PropertyListingSubmission(Base):
    """Draft workflow state for list-your-property stepper submissions."""

    __tablename__ = "property_listing_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_USERS_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_PROPERTIES_NORMALIZED_ID, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True, default="draft")
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_completed_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    step_completion: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    terms_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    privacy_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_display_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fees_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_USERS_ID, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_USERS_ID, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    delete_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
