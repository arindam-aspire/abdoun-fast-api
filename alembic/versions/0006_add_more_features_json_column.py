"""add more_features json column

Revision ID: 0006_more_features
Revises: 0005_drop_old_props
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_more_features"
down_revision = "0005_drop_old_props"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add more_features JSON column to properties_normalized table
    op.add_column(
        "properties_normalized",
        sa.Column("more_features", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    # Remove more_features column
    op.drop_column("properties_normalized", "more_features")

