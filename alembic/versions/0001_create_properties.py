"""create properties table with postgis

Revision ID: 0001_create_properties
Revises:
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2.types import Geometry


revision = "0001_create_properties"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    op.create_table(
        "properties",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("selling_price_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("selling_price_currency", sa.String(3), nullable=True),
        sa.Column("rent_price_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("rent_price_currency", sa.String(3), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("built_up_area", sa.Numeric(18, 2), nullable=True),
        sa.Column("features", sa.JSON(), nullable=True),
        sa.Column("more_features", sa.JSON(), nullable=True),
        sa.Column("images", sa.JSON(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "location",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_properties_location_gist",
        "properties",
        ["location"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("idx_properties_location_gist", table_name="properties")
    op.drop_table("properties")








