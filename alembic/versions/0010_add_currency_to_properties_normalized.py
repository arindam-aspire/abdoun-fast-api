"""add currency column to properties_normalized

Revision ID: 0010_currency
Revises: 0009_feature_value
Create Date: 2026-02-27

Single currency field for the property (e.g. JOD), derived from
CSV selling_price / rent_price on import.
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_currency"
down_revision = "0009_feature_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties_normalized",
        sa.Column("currency", sa.String(3), nullable=True),
    )
    # Backfill: set currency from rent_price_currency or selling_price_currency where null
    op.execute(
        sa.text("""
            UPDATE properties_normalized
            SET currency = COALESCE(rent_price_currency, selling_price_currency, 'JOD')
            WHERE currency IS NULL
        """)
    )


def downgrade() -> None:
    op.drop_column("properties_normalized", "currency")

