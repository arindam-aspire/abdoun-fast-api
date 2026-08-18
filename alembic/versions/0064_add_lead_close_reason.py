"""Add lead close reason.

Revision ID: 0064_add_lead_close_reason
Revises: 0063_lead_close_requests
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0064_add_lead_close_reason"
down_revision = "0063_lead_close_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("close_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "close_reason")
