"""drop old properties table

Revision ID: 0005_drop_old_props
Revises: 0004_normalized_tables
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_drop_old_props"
down_revision = "0004_normalized_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old properties table if it exists
    # First drop any indexes
    op.execute("DROP INDEX IF EXISTS ix_properties_url;")
    op.execute("DROP INDEX IF EXISTS ix_properties_location_name;")
    op.execute("DROP INDEX IF EXISTS ix_properties_id;")
    
    # Drop the table
    op.drop_table("properties")


def downgrade() -> None:
    # Recreate the old properties table (if needed for rollback)
    # Note: This is a simplified recreation - adjust based on your original schema
    op.create_table(
        "properties",
        sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
        sa.Column("url", sa.String(), nullable=True, unique=True, index=True),
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
        sa.Column("location_name", sa.String(), nullable=True, index=True),
        sa.Column(
            "location",
            sa.String(),  # Simplified - original was Geometry
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

