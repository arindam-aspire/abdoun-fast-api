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
    TIMESTAMP,
    UUID,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from app.models.property import Base


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
    category_id = Column(Integer, ForeignKey("property_categories.id"), nullable=False)
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
    category_id = Column(Integer, ForeignKey("property_categories.id"), nullable=False)
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
    category_id = Column(Integer, ForeignKey("property_categories.id"), nullable=False)
    feature_id = Column(Integer, ForeignKey("features.id"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# ==============================
# Type Features
# ==============================

class TypeFeature(Base):
    __tablename__ = "type_features"

    id = Column(Integer, primary_key=True, index=True)
    property_type_id = Column(Integer, ForeignKey("property_types.id"), nullable=False)
    feature_id = Column(Integer, ForeignKey("features.id"), nullable=False)
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

    category_id = Column(Integer, ForeignKey("property_categories.id"), nullable=False)
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

    price = Column(Numeric(15, 2), nullable=False)  # Primary price (selling or rent)
    selling_price_amount = Column(Numeric(15, 2), nullable=True)  # If available for sale
    selling_price_currency = Column(String(3), nullable=True)
    rent_price_amount = Column(Numeric(15, 2), nullable=True)  # If available for rent
    rent_price_currency = Column(String(3), nullable=True)

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


# ==============================
# Property Features
# ==============================

class PropertyFeature(Base):
    __tablename__ = "property_features"

    property_id = Column(UUID(as_uuid=True), ForeignKey("properties_normalized.id"), primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id"), primary_key=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    property = relationship("PropertyNormalized", back_populates="features")
    feature = relationship("Feature", foreign_keys=[feature_id])

