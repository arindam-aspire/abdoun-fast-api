from __future__ import annotations

from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class PropertyDealClosure(Base):
    __tablename__ = "property_deal_closures"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    lead_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True)
    agency_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("agency_master.id"), nullable=True)
    requested_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[Any] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    reason: Mapped[Any] = mapped_column(Text, nullable=True)
    review_reason: Mapped[Any] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    reviewed_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

