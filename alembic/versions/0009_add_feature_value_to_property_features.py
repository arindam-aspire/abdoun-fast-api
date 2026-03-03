"""add feature value column to property_features

Revision ID: 0009_feature_value
Revises: 0008_reference_number
Create Date: 2026-02-27

Stores per-property value for selected features such as
Finishing, Windows, Air Conditioning, Heating System, etc.
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_feature_value"
down_revision = "0008_reference_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_features",
        sa.Column("value", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("property_features", "value")


