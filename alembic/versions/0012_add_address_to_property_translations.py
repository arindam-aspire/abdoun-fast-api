"""add address column to property_translations

Revision ID: 0012_translation_address
Revises: 0011_pricing_extras
Create Date: 2026-03-02

Store localized address text (e.g. "Dair Gbhar - Amman", "دير غبار - عمان")
per language in property_translations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_translation_address"
down_revision = "0011_pricing_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_translations",
        sa.Column("address", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("property_translations", "address")

