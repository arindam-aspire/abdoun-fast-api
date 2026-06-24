"""SQLAlchemy mappings generated from the Phase 0 live DB schema inventory.

Do not hand-edit table definitions casually. Regenerate or patch intentionally
when the demo DB schema changes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    activity_type: Mapped[Any] = mapped_column(String(50), nullable=True)
    message: Mapped[Any] = mapped_column(Text, nullable=True)
    tone: Mapped[Any] = mapped_column(String(20), nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class LeadMessage(Base):
    __tablename__ = "lead_messages"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    lead_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    sender_user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    recipient_user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    message: Mapped[Any] = mapped_column(Text, nullable=False)
    channel: Mapped[Any] = mapped_column(String(6), nullable=False, server_default=text("'IN_APP'::lead_message_channel_enum"))
    delivery_state: Mapped[Any] = mapped_column(String(32), nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class City(Base):
    __tablename__ = "cities"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".cities_id_seq'::regclass)"))
    name: Mapped[Any] = mapped_column(String(100), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class DashboardSummary(Base):
    __tablename__ = "dashboard_summary"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_properties: Mapped[Any] = mapped_column(Integer, nullable=True)
    active_properties: Mapped[Any] = mapped_column(Integer, nullable=True)
    draft_properties: Mapped[Any] = mapped_column(Integer, nullable=True)
    total_views: Mapped[Any] = mapped_column(Integer, nullable=True)
    total_inquiries: Mapped[Any] = mapped_column(Integer, nullable=True)
    total_deals: Mapped[Any] = mapped_column(Integer, nullable=True)
    conversion_rate: Mapped[Any] = mapped_column(Numeric, nullable=True)
    last_updated: Mapped[Any] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class LeadNote(Base):
    __tablename__ = "lead_notes"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    lead_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    author_user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[Any] = mapped_column(Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class LeadStatusHistory(Base):
    __tablename__ = "lead_status_history"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    lead_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    from_status: Mapped[Any] = mapped_column(String(17), nullable=True)
    to_status: Mapped[Any] = mapped_column(String(17), nullable=False)
    actor_user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[Any] = mapped_column(String(32), nullable=True)
    reason: Mapped[Any] = mapped_column(Text, nullable=True)
    changed_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class LeadNumberCounter(Base):
    __tablename__ = "lead_number_counters"

    year: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".lead_number_counters_year_seq'::regclass)"))
    last_value: Mapped[Any] = mapped_column(Integer, nullable=False, server_default=text("0"))


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    notification_type: Mapped[Any] = mapped_column(String(100), nullable=False)
    enabled: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class AdminAgentAssignment(Base):
    __tablename__ = "admin_agent_assignments"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    admin_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    assigned_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    revoked_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    can_inherit_privileges: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class AgentInvite(Base):
    __tablename__ = "agent_invites"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    email: Mapped[Any] = mapped_column(String(255), nullable=False)
    invited_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token: Mapped[Any] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[Any] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    invited_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    revoked_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True, nullable=False)
    service_area: Mapped[Any] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    status: Mapped[Any] = mapped_column(String(20), nullable=False, server_default=text("'INVITED'::character varying"))
    reviewed_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    form_submitted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    password_set_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    decline_reason: Mapped[Any] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status_reason: Mapped[Any] = mapped_column(Text, nullable=True)


class CategoryFeature(Base):
    __tablename__ = "category_features"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".category_features_id_seq'::regclass)"))
    category_id: Mapped[Any] = mapped_column(Integer, ForeignKey("property_categories.id"), nullable=False)
    feature_id: Mapped[Any] = mapped_column(Integer, ForeignKey("features.id"), nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".features_id_seq'::regclass)"))
    name: Mapped[Any] = mapped_column(String(100), nullable=False)
    slug: Mapped[Any] = mapped_column(String(100), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    category_id: Mapped[Any] = mapped_column(Integer, ForeignKey("property_categories.id"), nullable=True)
    property_type_id: Mapped[Any] = mapped_column(Integer, ForeignKey("property_types.id"), nullable=True)
    feature_group: Mapped[Any] = mapped_column(String(50), nullable=False, server_default=text("'FEATURE'::character varying"))
    display_order: Mapped[Any] = mapped_column(Integer, nullable=False, server_default=text("0"))


class CategorySearchField(Base):
    __tablename__ = "category_search_fields"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".category_search_fields_id_seq'::regclass)"))
    category_id: Mapped[Any] = mapped_column(Integer, ForeignKey("property_categories.id"), nullable=False)
    field_id: Mapped[Any] = mapped_column(Integer, ForeignKey("search_fields.id"), nullable=False)
    is_required: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    inquiry_type: Mapped[Any] = mapped_column(String(50), nullable=True)
    message: Mapped[Any] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    status: Mapped[Any] = mapped_column(String(17), nullable=False, server_default=text("'NEW'::lead_status_enum"))
    source: Mapped[Any] = mapped_column(String(14), nullable=False, server_default=text("'EMAIL_FORM'::lead_source_enum"))
    assigned_agent_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_by_admin_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_activity_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    request_close_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    closed_by_admin_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    lead_number: Mapped[Any] = mapped_column(String(32), nullable=False)
    external_owner_name: Mapped[Any] = mapped_column(String(255), nullable=True)
    external_owner_phone: Mapped[Any] = mapped_column(String(50), nullable=True)
    external_owner_email: Mapped[Any] = mapped_column(String(255), nullable=True)
    external_property_name: Mapped[Any] = mapped_column(String(255), nullable=True)
    communication_mode: Mapped[Any] = mapped_column(String(32), nullable=False, server_default=text("'IN_APP'::character varying"))
    created_by_agent_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    offline_inquiry_type: Mapped[Any] = mapped_column(String(64), nullable=True)
    offline_source: Mapped[Any] = mapped_column(String(64), nullable=True)
    offline_notes: Mapped[Any] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class AgencyMaster(Base):
    __tablename__ = "agency_master"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    agency_name: Mapped[Any] = mapped_column(String(255), nullable=False)
    agency_trade_name: Mapped[Any] = mapped_column(String(255), nullable=False)
    legal_document_s3_link: Mapped[Any] = mapped_column(Text, nullable=False)
    email: Mapped[Any] = mapped_column(String(255), nullable=False)
    phone: Mapped[Any] = mapped_column(String(20), nullable=False)
    website: Mapped[Any] = mapped_column(String(255), nullable=True)
    address: Mapped[Any] = mapped_column(Text, nullable=True)
    city: Mapped[Any] = mapped_column(String(100), nullable=True)
    state: Mapped[Any] = mapped_column(String(100), nullable=True)
    country: Mapped[Any] = mapped_column(String(100), nullable=True)
    zip_code: Mapped[Any] = mapped_column(String(20), nullable=True)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_verified: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    logo_url: Mapped[Any] = mapped_column(Text, nullable=True)
    currency: Mapped[Any] = mapped_column(String(3), nullable=False, server_default=text("'JOD'::character varying"))
    measurement_unit: Mapped[Any] = mapped_column(String(20), nullable=False, server_default=text("'sqm'::character varying"))


class PropertyListingSubmission(Base):
    __tablename__ = "property_listing_submissions"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    submitted_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agency_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("agency_master.id"), nullable=True)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[Any] = mapped_column(String(30), nullable=False, server_default=text("'draft'::character varying"))
    current_step: Mapped[Any] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_completed_step: Mapped[Any] = mapped_column(Integer, nullable=False, server_default=text("0"))
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    step_completion: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    terms_accepted: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    privacy_accepted: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    public_display_authorized: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fees_acknowledged: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    submitted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    reviewed_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    review_reason: Mapped[Any] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    delete_reason: Mapped[Any] = mapped_column(Text, nullable=True)


class PropertyFeature(Base):
    __tablename__ = "property_features"

    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    feature_id: Mapped[Any] = mapped_column(Integer, ForeignKey("features.id"), primary_key=True, nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    value: Mapped[Any] = mapped_column(String(255), nullable=True)


class PropertyCategory(Base):
    __tablename__ = "property_categories"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".property_categories_id_seq'::regclass)"))
    name: Mapped[Any] = mapped_column(String(100), nullable=False)
    slug: Mapped[Any] = mapped_column(String(100), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    recipient_user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    actor_user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    type_key: Mapped[Any] = mapped_column(String(100), nullable=False)
    title: Mapped[Any] = mapped_column(String(255), nullable=False)
    message: Mapped[Any] = mapped_column(Text, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=True)
    is_read: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    read_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[Any] = mapped_column(String(255), nullable=True)
    event_type: Mapped[Any] = mapped_column(String(100), nullable=True)
    action_url: Mapped[Any] = mapped_column(Text, nullable=True)


class Owner(Base):
    __tablename__ = "owner"

    owner_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    full_name: Mapped[Any] = mapped_column(String(100), nullable=True)
    email: Mapped[Any] = mapped_column(String(150), nullable=True)
    phone: Mapped[Any] = mapped_column(String(20), nullable=True)
    nationality: Mapped[Any] = mapped_column(String(100), nullable=True)
    ssi: Mapped[Any] = mapped_column(String(50), nullable=True)
    address: Mapped[Any] = mapped_column(Text, nullable=True)
    documents: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    code: Mapped[Any] = mapped_column(String(100), nullable=False)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class PropertyMedia(Base):
    __tablename__ = "property_media"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".property_media_id_seq'::regclass)"))
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    media_type: Mapped[Any] = mapped_column(String(20), nullable=False)
    url: Mapped[Any] = mapped_column(Text, nullable=False)
    thumb_url: Mapped[Any] = mapped_column(Text, nullable=True)
    is_primary: Mapped[Any] = mapped_column(Boolean, nullable=True, server_default=text("false"))
    display_order: Mapped[Any] = mapped_column(Integer, nullable=True, server_default=text("0"))
    caption: Mapped[Any] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class PropertyStatus(Base):
    __tablename__ = "property_status"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".property_status_id_seq'::regclass)"))
    name: Mapped[Any] = mapped_column(String(50), nullable=False)
    slug: Mapped[Any] = mapped_column(String(50), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class PropertyTranslation(Base):
    __tablename__ = "property_translations"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".property_translations_id_seq'::regclass)"))
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    language_code: Mapped[Any] = mapped_column(String(5), nullable=False)
    title: Mapped[Any] = mapped_column(Text, nullable=True)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    address: Mapped[Any] = mapped_column(Text, nullable=True)


class PropertyView(Base):
    __tablename__ = "property_views"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_type: Mapped[Any] = mapped_column(String(10), nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=True)
    viewed_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider: Mapped[Any] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[Any] = mapped_column(String(255), nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class UserPropertyFavorite(Base):
    __tablename__ = "user_property_favorites"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True, nullable=False)
    role_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True, nullable=False)
    assigned_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class UserAgencyMapping(Base):
    __tablename__ = "user_agency_mappings"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agency_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("agency_master.id"), nullable=False)
    relationship_type: Mapped[Any] = mapped_column(String(40), nullable=False)
    status: Mapped[Any] = mapped_column(String(20), nullable=False, server_default=text("'active'::character varying"))
    is_primary: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    deleted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)


class SearchField(Base):
    __tablename__ = "search_fields"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".search_fields_id_seq'::regclass)"))
    name: Mapped[Any] = mapped_column(String(100), nullable=False)
    field_key: Mapped[Any] = mapped_column(String(100), nullable=False)
    field_type: Mapped[Any] = mapped_column(String(50), nullable=True)
    is_range: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class PropertyType(Base):
    __tablename__ = "property_types"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".property_types_id_seq'::regclass)"))
    category_id: Mapped[Any] = mapped_column(Integer, ForeignKey("property_categories.id"), nullable=False)
    name: Mapped[Any] = mapped_column(String(100), nullable=False)
    slug: Mapped[Any] = mapped_column(String(100), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class RecentlyViewedProperty(Base):
    __tablename__ = "recently_viewed_properties"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    viewed_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True, nullable=False)
    permission_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True, nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    name: Mapped[Any] = mapped_column(String(50), nullable=False)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class TypeFeature(Base):
    __tablename__ = "type_features"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".type_features_id_seq'::regclass)"))
    property_type_id: Mapped[Any] = mapped_column(Integer, ForeignKey("property_types.id"), nullable=False)
    feature_id: Mapped[Any] = mapped_column(Integer, ForeignKey("features.id"), nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class UserProfileChangeChallenge(Base):
    __tablename__ = "user_profile_change_challenges"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    purpose: Mapped[Any] = mapped_column(String(16), nullable=False)
    new_value: Mapped[Any] = mapped_column(String(255), nullable=False)
    otp_hash: Mapped[Any] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[Any] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    cognito_custom_auth_session: Mapped[Any] = mapped_column(Text, nullable=True)


class UserRememberMeSession(Base):
    __tablename__ = "user_remember_me_sessions"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[Any] = mapped_column(String(64), nullable=False)
    cognito_refresh_encrypted: Mapped[Any] = mapped_column(Text, nullable=False)
    cognito_username: Mapped[Any] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[Any] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    last_used_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[Any] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Any] = mapped_column(String(45), nullable=True)


class UserSavedSearch(Base):
    __tablename__ = "user_saved_searches"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[Any] = mapped_column(String(255), nullable=False)
    search_criteria: Mapped[Any] = mapped_column(JSONB, nullable=False)
    notification_enabled: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_run_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


class User(Base):
    __tablename__ = "users"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    cognito_sub: Mapped[Any] = mapped_column(String(100), nullable=True)
    full_name: Mapped[Any] = mapped_column(String(255), nullable=False)
    email: Mapped[Any] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[Any] = mapped_column(String(20), nullable=True)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_email_verified: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_phone_verified: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    profile_picture_url: Mapped[Any] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    preferred_language: Mapped[Any] = mapped_column(String(10), nullable=False)
    password_login_failed_attempts: Mapped[Any] = mapped_column(Integer, nullable=False, server_default=text("0"))
    password_login_first_failed_at: Mapped[Any] = mapped_column(DateTime, nullable=True)
    password_login_locked_until: Mapped[Any] = mapped_column(DateTime, nullable=True)
    agency_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("agency_master.id"), nullable=True)
    password_hash: Mapped[Any] = mapped_column(String(255), nullable=True)


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[Any] = mapped_column(Integer, primary_key=True, nullable=False, server_default=text("nextval('\"public\".areas_id_seq'::regclass)"))
    city_id: Mapped[Any] = mapped_column(Integer, ForeignKey("cities.id"), nullable=False)
    name: Mapped[Any] = mapped_column(String(100), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=True, server_default=text("now()"))


class PropertyOwner(Base):
    __tablename__ = "property_owner"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    property_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("owner.owner_id"), nullable=False)
    is_active: Mapped[Any] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[Any] = mapped_column(DateTime, nullable=False, server_default=text("now()"))


__all__ = [
    "ActivityLog",
    "AdminAgentAssignment",
    "AgencyMaster",
    "AgentInvite",
    "AgentProfile",
    "Area",
    "CategoryFeature",
    "CategorySearchField",
    "City",
    "DashboardSummary",
    "Feature",
    "Lead",
    "LeadMessage",
    "LeadNote",
    "LeadNumberCounter",
    "LeadStatusHistory",
    "Notification",
    "NotificationPreference",
    "Owner",
    "Permission",
    "PropertyCategory",
    "PropertyFeature",
    "PropertyListingSubmission",
    "PropertyMedia",
    "PropertyOwner",
    "PropertyStatus",
    "PropertyTranslation",
    "PropertyType",
    "PropertyView",
    "RecentlyViewedProperty",
    "Role",
    "RolePermission",
    "SearchField",
    "SocialAccount",
    "TypeFeature",
    "User",
    "UserAgencyMapping",
    "UserProfileChangeChallenge",
    "UserPropertyFavorite",
    "UserRememberMeSession",
    "UserRole",
    "UserSavedSearch",
]
