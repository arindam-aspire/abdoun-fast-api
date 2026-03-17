"""
Normalized property models with separate tables for categories, types, cities, areas, features, etc.
"""
import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Column,
    DECIMAL,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UUID,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from app.models.property import Base

FK_PROPERTY_CATEGORIES_ID = "property_categories.id"
FK_FEATURES_ID = "features.id"
FK_PROPERTIES_NORMALIZED_ID = "properties_normalized.id"


# ==============================
# Property Categories
# ==============================

class PropertyCategory(Base):
    __tablename__ = "property_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    property_types = relationship("PropertyType", back_populates="category")


# ==============================
# Property Types
# ==============================

class PropertyType(Base):
    __tablename__ = "property_types"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    category = relationship("PropertyCategory", back_populates="property_types")


# ==============================
# Cities
# ==============================

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    areas = relationship("Area", back_populates="city")


# ==============================
# Areas
# ==============================

class Area(Base):
    __tablename__ = "areas"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    city = relationship("City", back_populates="areas")


# ==============================
# Search Fields
# ==============================

class SearchField(Base):
    __tablename__ = "search_fields"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    field_key = Column(String(100), unique=True, nullable=False)
    field_type = Column(String(50))
    is_range = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Category Search Fields
# ==============================

class CategorySearchField(Base):
    __tablename__ = "category_search_fields"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False)
    field_id = Column(Integer, ForeignKey("search_fields.id"), nullable=False)
    is_required = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Features
# ==============================

class Feature(Base):
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Category Features
# ==============================

class CategoryFeature(Base):
    __tablename__ = "category_features"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False)
    feature_id = Column(Integer, ForeignKey(FK_FEATURES_ID), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Type Features
# ==============================

class TypeFeature(Base):
    __tablename__ = "type_features"

    id = Column(Integer, primary_key=True, index=True)
    property_type_id = Column(Integer, ForeignKey("property_types.id"), nullable=False)
    feature_id = Column(Integer, ForeignKey(FK_FEATURES_ID), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Property Status
# ==============================

class PropertyStatus(Base):
    __tablename__ = "property_status"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Properties
# ==============================

class PropertyNormalized(Base):
    __tablename__ = "properties_normalized"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Deterministic hash of UUID for friendly integer IDs and fast lookups (indexed).
    # Range: 0..1e9-1 (matches app.schemas.property.uuid_to_int_hash).
    property_hash = Column(Integer, nullable=False, index=True)

    category_id = Column(Integer, ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False)
    type_id = Column(Integer, ForeignKey("property_types.id"), nullable=False)
    property_status_id = Column(Integer, ForeignKey("property_status.id"), nullable=False)

    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("areas.id"), nullable=False)

    # Original URL for reference
    url = Column(String, nullable=True, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)

    is_exclusive = Column(Boolean, default=False)
    is_featured = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)

    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    location = Column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    location_name = Column(String, nullable=True, index=True)  # For backward compatibility

    # Display reference from source (e.g. CSV property_id "01002") for SEO and listing
    reference_number = Column(String(50), nullable=True, index=True)

    price = Column(Numeric(15, 2), nullable=False)  # Primary price (selling or rent)
    currency = Column(String(3), nullable=True)  # Single currency for this property (from CSV selling_price/rent_price)
    selling_price_amount = Column(Numeric(15, 2), nullable=True)  # If available for sale
    selling_price_currency = Column(String(3), nullable=True)
    rent_price_amount = Column(Numeric(15, 2), nullable=True)  # If available for rent
    rent_price_currency = Column(String(3), nullable=True)

    # From CSV: rent_commission ("5.00 %"), contract_duration ("Undefined"), payment_method ("Annual")
    rent_commission_percent = Column(Numeric(5, 2), nullable=True)
    contract_duration = Column(String(50), nullable=True)
    payment_method = Column(String(50), nullable=True)

    area = Column(Numeric(10, 2))  # Built-up area
    plot_area = Column(Numeric(10, 2))  # Plot/land area

    bedrooms = Column(Integer)
    bathrooms = Column(Integer)
    rooms = Column(Integer)

    furniture_status = Column(String(50))
    parking = Column(Boolean)
    property_age = Column(Integer)

    # Store images as JSON array for now (can be normalized later)
    images = Column(String)  # JSON array of image URLs
    
    # Store more_features as JSON object (key-value pairs)
    more_features = Column(JSON, nullable=True)  # JSON object with key-value pairs

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    category = relationship("PropertyCategory", foreign_keys=[category_id])
    type = relationship("PropertyType", foreign_keys=[type_id])
    property_status = relationship("PropertyStatus", foreign_keys=[property_status_id])
    city = relationship("City", foreign_keys=[city_id])
    area_rel = relationship("Area", foreign_keys=[location_id])
    
    features = relationship(
        "PropertyFeature",
        back_populates="property",
        cascade="all, delete"
    )
    translations = relationship(
        "PropertyTranslation",
        back_populates="property",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    media_items = relationship(
        "PropertyMedia",
        back_populates="property",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PropertyMedia.display_order",
    )


# ==============================
# Property Translations (i18n)
# ==============================
# Best practice: separate table for title/description per language.
# Slug is NOT translated; derive from title when needed for SEO.
# UNIQUE(property_id, language_code) in DB ensures one row per language per property.

class PropertyTranslation(Base):
    __tablename__ = "property_translations"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(UUID(as_uuid=True), ForeignKey(FK_PROPERTIES_NORMALIZED_ID, ondelete="CASCADE"), nullable=False)
    language_code = Column(String(5), nullable=False)  # 'en', 'ar', 'esp', 'fr'
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    address = Column(Text, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("property_id", "language_code", name="uq_property_translations_property_lang"),)

    property = relationship("PropertyNormalized", back_populates="translations")


# ==============================
# Property Features
# ==============================

class PropertyFeature(Base):
    __tablename__ = "property_features"

    property_id = Column(UUID(as_uuid=True), ForeignKey(FK_PROPERTIES_NORMALIZED_ID), primary_key=True)
    feature_id = Column(Integer, ForeignKey(FK_FEATURES_ID), primary_key=True)

    # Optional per-property value for this feature (e.g. Finishing=Deluxe)
    value = Column(String(255), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    property = relationship("PropertyNormalized", back_populates="features")
    feature = relationship("Feature", foreign_keys=[feature_id])


# ==============================
# Property Media
# ==============================

class PropertyMedia(Base):
    __tablename__ = "property_media"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(
        UUID(as_uuid=True),
        ForeignKey(FK_PROPERTIES_NORMALIZED_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_type = Column(String(20), nullable=False)  # image | video | floor_plan | document
    url = Column(Text, nullable=False)
    thumb_url = Column(Text, nullable=True)
    is_primary = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    caption = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    property = relationship("PropertyNormalized", back_populates="media_items")
