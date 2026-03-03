"""add reference_number to properties_normalized

Revision ID: 0008_reference_number
Revises: 0007_property_translations
Create Date: 2026-02-27

Stores display reference from CSV property_id (e.g. 01002) for SEO and listing.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_reference_number"
down_revision = "0007_property_translations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties_normalized",
        sa.Column("reference_number", sa.String(50), nullable=True),
    )
    op.create_index(
        "idx_properties_normalized_reference_number",
        "properties_normalized",
        ["reference_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_properties_normalized_reference_number", table_name="properties_normalized")
    op.drop_column("properties_normalized", "reference_number")
