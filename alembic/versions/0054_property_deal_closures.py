"""add property deal closure requests

Revision ID: 0054_property_deal_closures
Revises: 0053_owner_soft_delete
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0054_property_deal_closures"
down_revision = "0053_owner_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_deal_closures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agency_master.id"), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_property_deal_closures_property_id", "property_deal_closures", ["property_id"])
    op.create_index("ix_property_deal_closures_agency_status", "property_deal_closures", ["agency_id", "status"])
    op.create_index("ix_property_deal_closures_status", "property_deal_closures", ["status"])


def downgrade() -> None:
    op.drop_index("ix_property_deal_closures_status", table_name="property_deal_closures")
    op.drop_index("ix_property_deal_closures_agency_status", table_name="property_deal_closures")
    op.drop_index("ix_property_deal_closures_property_id", table_name="property_deal_closures")
    op.drop_table("property_deal_closures")

