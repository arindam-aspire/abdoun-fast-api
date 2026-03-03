"""add rent_commission_percent, contract_duration, payment_method to properties_normalized

Revision ID: 0011_pricing_extras
Revises: 0010_currency
Create Date: 2026-02-27

From CSV: rent_commission ("5.00 %"), contract_duration ("Undefined"), payment_method ("Annual").
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_pricing_extras"
down_revision = "0010_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties_normalized",
        sa.Column("rent_commission_percent", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("contract_duration", sa.String(50), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("payment_method", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties_normalized", "payment_method")
    op.drop_column("properties_normalized", "contract_duration")
    op.drop_column("properties_normalized", "rent_commission_percent")

