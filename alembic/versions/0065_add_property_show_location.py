"""Add show_location to property listing submissions.

Revision ID: 0065_add_property_show_location
Revises: 0064_add_lead_close_reason
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0065_add_property_show_location"
down_revision = "0064_add_lead_close_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_listing_submissions",
        sa.Column("show_location", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("property_listing_submissions", "show_location")
