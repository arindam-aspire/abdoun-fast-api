"""Recently viewed properties model for per-user recency tracking."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.property import Base

FK_USERS_ID = "users.id"
FK_PROPERTIES_ID = "properties_normalized.id"


class RecentlyViewedProperty(Base):
    """Per-user recently viewed property record (max 10 rows managed in service)."""

    __tablename__ = "recently_viewed_properties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_USERS_ID, ondelete="CASCADE"),
        nullable=False,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(FK_PROPERTIES_ID, ondelete="CASCADE"),
        nullable=False,
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="recent_views")
    property = relationship("PropertyNormalized", back_populates="recently_viewed_by")

    __table_args__ = (
        UniqueConstraint("user_id", "property_id", name="uq_recent_views_user_property"),
        Index("ix_recent_views_user_viewed_at_desc", "user_id", viewed_at.desc()),
    )
