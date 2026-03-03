"""create normalized property tables

Revision ID: 0004_normalized_tables
Revises: 0003_add_location_name
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2.types import Geometry
import uuid


revision = "0004_normalized_tables"
down_revision = "0003_add_location_name"
branch_labels = None
depends_on = None

FK_PROPERTY_CATEGORIES_ID = "property_categories.id"
FK_FEATURES_ID = "features.id"


def upgrade() -> None:
    # Property Categories
    op.create_table(
        "property_categories",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Property Types
    op.create_table(
        "property_types",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Cities
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Areas
    op.create_table(
        "areas",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("city_id", sa.Integer(), sa.ForeignKey("cities.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Search Fields
    op.create_table(
        "search_fields",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("field_key", sa.String(100), unique=True, nullable=False),
        sa.Column("field_type", sa.String(50)),
        sa.Column("is_range", sa.Boolean(), default=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Category Search Fields
    op.create_table(
        "category_search_fields",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("search_fields.id"), nullable=False),
        sa.Column("is_required", sa.Boolean(), default=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Features
    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Category Features
    op.create_table(
        "category_features",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey(FK_FEATURES_ID), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Type Features
    op.create_table(
        "type_features",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("property_type_id", sa.Integer(), sa.ForeignKey("property_types.id"), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey(FK_FEATURES_ID), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Property Status
    op.create_table(
        "property_status",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("slug", sa.String(50), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Properties Normalized
    op.create_table(
        "properties_normalized",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey(FK_PROPERTY_CATEGORIES_ID), nullable=False),
        sa.Column("type_id", sa.Integer(), sa.ForeignKey("property_types.id"), nullable=False),
        sa.Column("property_status_id", sa.Integer(), sa.ForeignKey("property_status.id"), nullable=False),
        sa.Column("city_id", sa.Integer(), sa.ForeignKey("cities.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("areas.id"), nullable=False),
        sa.Column("url", sa.String(), nullable=True, unique=True, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_exclusive", sa.Boolean(), default=False),
        sa.Column("is_featured", sa.Boolean(), default=False),
        sa.Column("is_verified", sa.Boolean(), default=False),
        sa.Column("latitude", sa.DECIMAL(10, 8)),
        sa.Column("longitude", sa.DECIMAL(11, 8)),
        sa.Column(
            "location",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("location_name", sa.String(), nullable=True, index=True),
        sa.Column("price", sa.Numeric(15, 2), nullable=False),
        sa.Column("selling_price_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("selling_price_currency", sa.String(3), nullable=True),
        sa.Column("rent_price_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("rent_price_currency", sa.String(3), nullable=True),
        sa.Column("area", sa.Numeric(10, 2)),
        sa.Column("plot_area", sa.Numeric(10, 2)),
        sa.Column("bedrooms", sa.Integer()),
        sa.Column("bathrooms", sa.Integer()),
        sa.Column("rooms", sa.Integer()),
        sa.Column("furniture_status", sa.String(50)),
        sa.Column("parking", sa.Boolean()),
        sa.Column("property_age", sa.Integer()),
        sa.Column("images", sa.String()),  # JSON array as string
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Property Features (many-to-many)
    op.create_table(
        "property_features",
        sa.Column("property_id", sa.UUID(as_uuid=True), sa.ForeignKey("properties_normalized.id"), primary_key=True),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey(FK_FEATURES_ID), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("property_features")
    op.drop_table("properties_normalized")
    op.drop_table("property_status")
    op.drop_table("type_features")
    op.drop_table("category_features")
    op.drop_table("features")
    op.drop_table("category_search_fields")
    op.drop_table("search_fields")
    op.drop_table("areas")
    op.drop_table("cities")
    op.drop_table("property_types")
    op.drop_table("property_categories")

