"""Add route_through_agency to property listing submissions.

Revision ID: 0067_route_through_agency
Revises: 0066_property_ref_number
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0067_route_through_agency"
down_revision = "0066_property_ref_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_listing_submissions",
        sa.Column("route_through_agency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions
            SET route_through_agency = true
            WHERE agency_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("property_listing_submissions", "route_through_agency")
