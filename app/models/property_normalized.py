"""Normalized property ORM models: categories, types, cities, areas, features, properties, translations, media."""
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Column,
    DECIMAL,
    DateTime,
    Enum,
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
from sqlalchemy.orm import relationship

from app.models.property import Base

FK_PROPERTY_CATEGORIES_ID = "property_categories.id"
FK_FEATURES_ID = "features.id"
FK_PROPERTIES_NORMALIZED_ID = "properties_normalized.id"
FK_USERS_ID = "users.id"
FK_AGENCY_MASTER_ID = "agency_master.id"
ONDELETE_SET_NULL = "SET NULL"
CASCADE_DELETE_ORPHAN = "all, delete-orphan"


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
    features = relationship("Feature", back_populates="category")


# ==============================
# Property Types
# ==============================

class PropertyType(Base):
    """Property type within a category (e.g. apartment, villa)."""
    __tablename__ = "property_types"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    category = relationship("PropertyCategory", back_populates="property_types")
    features = relationship("Feature", back_populates="property_type")


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
    """Area or district within a city."""
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
    """Searchable field definition (key, type, range)."""
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
    """Link between category and search field (required/optional)."""
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
    """Feature or amenity (e.g. pool, parking) that can be attached to properties."""
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    category_id = Column(Integer, ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=True, index=True)
    property_type_id = Column(Integer, ForeignKey("property_types.id"), nullable=True, index=True)
    feature_group = Column(String(50), nullable=False, server_default="FEATURE", index=True)
    display_order = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    category = relationship("PropertyCategory", back_populates="features")
    property_type = relationship("PropertyType", back_populates="features")


# ==============================
# Category Features
# ==============================

class CategoryFeature(Base):
    """Link between category and available feature."""
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
    """Link between property type and feature."""
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
    """Listing status (e.g. available, sold)."""
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
    """Main property listing with category, type, location, price, and relationships."""
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
    listing_purpose = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)

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
    parking_spaces = Column(Integer, nullable=True)
    property_age = Column(Integer)
    total_floors = Column(Integer, nullable=True)
    completion_status = Column(String(50), nullable=True)
    occupancy = Column(String(50), nullable=True)
    ownership_type = Column(String(50), nullable=True)
    permit_number = Column(String(100), nullable=True)
    orientation = Column(String(50), nullable=True)
    service_charge = Column(Numeric(15, 2), nullable=True)
    maintenance_fee = Column(Numeric(15, 2), nullable=True)
    youtube_url = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    agency_id = Column(
        UUID(as_uuid=True),
        ForeignKey(FK_AGENCY_MASTER_ID, ondelete=ONDELETE_SET_NULL),
        nullable=True,
        index=True,
    )

    # Store images as JSON array for now (can be normalized later)
    images = Column(String)  # JSON array of image URLs
    virtual_tour_url = Column(Text, nullable=True)
    
    # Store more_features as JSON object (key-value pairs)
    more_features = Column(JSON, nullable=True)  # JSON object with key-value pairs

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True)
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True)
    deal_closed = Column(Boolean, default=False, nullable=False)

    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True)
    delete_reason = Column(Text, nullable=True)

    # Relationships
    category = relationship("PropertyCategory", foreign_keys=[category_id])
    type = relationship("PropertyType", foreign_keys=[type_id])
    property_status = relationship("PropertyStatus", foreign_keys=[property_status_id])
    city = relationship("City", foreign_keys=[city_id])
    area_rel = relationship("Area", foreign_keys=[location_id])

    # User relationships (assignment + auditing)
    # - For admin-created properties, agent_user will be null until explicitly assigned.
    # - For agent-created properties, created_by_user will typically be that agent.
    created_by_user = relationship("User", foreign_keys=[created_by], lazy="selectin")
    agent_user = relationship("User", foreign_keys=[agent_user_id], lazy="selectin")
    agency = relationship("Agency", foreign_keys=[agency_id], lazy="selectin")
    
    features = relationship(
        "PropertyFeature",
        back_populates="property",
        cascade="all, delete"
    )
    translations = relationship(
        "PropertyTranslation",
        back_populates="property",
        cascade=CASCADE_DELETE_ORPHAN,
        lazy="selectin",
    )
    media_items = relationship(
        "PropertyMedia",
        back_populates="property",
        cascade=CASCADE_DELETE_ORPHAN,
        lazy="selectin",
        order_by="PropertyMedia.display_order",
    )
    recently_viewed_by = relationship(
        "RecentlyViewedProperty",
        back_populates="property",
        cascade="all, delete-orphan",
    )


# ==============================
# Property Translations (i18n)
# ==============================
# Best practice: separate table for title/description per language.
# Slug is NOT translated; derive from title when needed for SEO.
# UNIQUE(property_id, language_code) in DB ensures one row per language per property.

class PropertyTranslation(Base):
    """Per-language title, description, address for a property (i18n)."""
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
    """Many-to-many: property to feature with optional value."""
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
    """Media item (image, video, floor plan) for a property with display order."""
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


class Lead(Base):
    """Inquiry lead generated for a property."""

    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey(FK_PROPERTIES_NORMALIZED_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    inquiry_type = Column(String(50), nullable=True)
    status = Column(
        Enum("NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED", name="lead_status_enum"),
        nullable=False,
        server_default="NEW",
        index=True,
    )
    source = Column(
        Enum(
            "EMAIL_FORM",
            "PHONE",
            "WHATSAPP",
            "MANUAL_ADMIN",
            "AGENT_MANUAL",
            "OFFLINE_MANUAL",
            name="lead_source_enum",
        ),
        nullable=False,
        server_default="EMAIL_FORM",
        index=True,
    )
    assigned_agent_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True)
    assigned_by_admin_id = Column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True
    )
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    request_close_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_admin_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    message = Column(Text, nullable=True)
    lead_number = Column(String(32), nullable=False, unique=True, index=True)
    external_owner_name = Column(String(255), nullable=True)
    external_owner_phone = Column(String(50), nullable=True)
    external_owner_email = Column(String(255), nullable=True)
    external_property_name = Column(String(255), nullable=True)
    communication_mode = Column(String(32), nullable=False, server_default="IN_APP")
    created_by_agent_id = Column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True
    )
    offline_inquiry_type = Column(String(64), nullable=True)
    offline_source = Column(String(64), nullable=True)
    offline_notes = Column(Text, nullable=True)
    created_by_admin_id = Column(
        UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class LeadStatusHistory(Base):
    """Audit trail for lead status transitions."""

    __tablename__ = "lead_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(
        Enum("NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED", name="lead_status_enum"),
        nullable=True,
    )
    to_status = Column(
        Enum("NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED", name="lead_status_enum"),
        nullable=False,
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    actor_role = Column(String(32), nullable=True)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class LeadNote(Base):
    """Internal lead notes visible to scoped agents/admins only."""

    __tablename__ = "lead_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class LeadMessage(Base):
    """Lead reply message records and delivery-channel metadata."""

    __tablename__ = "lead_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    recipient_user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    message = Column(Text, nullable=False)
    channel = Column(
        Enum("IN_APP", "EMAIL", name="lead_message_channel_enum"),
        nullable=False,
        server_default="IN_APP",
    )
    delivery_state = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class PropertyView(Base):
    """View event for a property."""

    __tablename__ = "property_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey(FK_PROPERTIES_NORMALIZED_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    user_type = Column(Enum("guest", "registered", name="property_view_user_type"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ActivityLog(Base):
    """Activity feed row used in dashboard summary timeline."""

    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    property_id = Column(UUID(as_uuid=True), ForeignKey(FK_PROPERTIES_NORMALIZED_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    activity_type = Column(String(50), nullable=True)
    message = Column(Text, nullable=True)
    tone = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DashboardSummary(Base):
    """Materialized snapshot of dashboard metrics per user."""

    __tablename__ = "dashboard_summary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey(FK_USERS_ID, ondelete=ONDELETE_SET_NULL), nullable=True)
    total_properties = Column(Integer, nullable=True)
    active_properties = Column(Integer, nullable=True)
    draft_properties = Column(Integer, nullable=True)
    total_views = Column(Integer, nullable=True)
    total_inquiries = Column(Integer, nullable=True)
    total_deals = Column(Integer, nullable=True)
    conversion_rate = Column(Numeric, nullable=True)
    last_updated = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
