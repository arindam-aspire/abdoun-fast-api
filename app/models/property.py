# from datetime import datetime
# from typing import Any

# from geoalchemy2 import Geometry  # Commented out - not needed when Property is commented
from sqlalchemy import String, Integer, Numeric, JSON, DateTime, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ==============================
# OLD PROPERTY MODEL - COMMENTED OUT
# Using normalized structure in property_normalized.py instead
# ==============================

# class Property(Base):
#     __tablename__ = "properties"
#
#     id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
#     url: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
#     title: Mapped[str] = mapped_column(String, nullable=False)
#     description: Mapped[str | None] = mapped_column(String, nullable=True)
#     category: Mapped[str | None] = mapped_column(String, nullable=True)
#     status: Mapped[str | None] = mapped_column(String, nullable=True)
#
#     selling_price_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
#     selling_price_currency: Mapped[str | None] = mapped_column(String(3))
#
#     rent_price_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
#     rent_price_currency: Mapped[str | None] = mapped_column(String(3))
#
#     bedrooms: Mapped[int | None] = mapped_column(Integer)
#     bathrooms: Mapped[int | None] = mapped_column(Integer)
#     built_up_area: Mapped[float | None] = mapped_column(Numeric(18, 2))
#
#     features: Mapped[list[Any] | None] = mapped_column(JSON)
#     more_features: Mapped[list[Any] | None] = mapped_column(JSON)
#     images: Mapped[list[str] | None] = mapped_column(JSON)
#
#     latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
#     longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
#
#     # Location name (human-readable, e.g., "Dabouq - Amman")
#     # NOT redundant with geometry - complementary:
#     # - Geometry: for spatial queries and map rendering
#     # - Location name: for display, text search, and user experience
#     location_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
#
#     location: Mapped[Any] = mapped_column(
#         Geometry(geometry_type="POINT", srid=4326),
#         nullable=True,
#     )
#
#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now()
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#     )








