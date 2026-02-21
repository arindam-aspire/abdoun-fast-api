"""add location_name column

Revision ID: 0003_add_location_name
Revises: 0002_add_integer_id
Create Date: 2026-02-17 18:50:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_add_location_name"
down_revision = "0002_add_integer_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add location_name column for human-readable location text
    # This is NOT redundant with geometry - it's complementary:
    # - Geometry: for spatial queries and map rendering
    # - Location name: for display, text search, and user experience
    op.add_column(
        "properties",
        sa.Column("location_name", sa.String(), nullable=True),
    )
    
    # Create index for text search on location names
    op.create_index(
        "ix_properties_location_name",
        "properties",
        ["location_name"],
        unique=False,
    )


def downgrade() -> None:
    # Remove index first
    op.drop_index("ix_properties_location_name", table_name="properties")
    
    # Remove column
    op.drop_column("properties", "location_name")

