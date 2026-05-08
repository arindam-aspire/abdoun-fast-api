"""Add manual owner lead fields.

Revision ID: 0041_manual_owner_leads
Revises: 0040_lead_display_identifiers
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0041_manual_owner_leads"
down_revision: Union[str, Sequence[str], None] = "0040_lead_display_identifiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE lead_source_enum ADD VALUE IF NOT EXISTS 'AGENT_MANUAL'")

    op.add_column("leads", sa.Column("external_owner_name", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("external_owner_phone", sa.String(length=50), nullable=True))
    op.add_column("leads", sa.Column("external_owner_email", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("external_property_name", sa.String(length=255), nullable=True))
    op.add_column(
        "leads",
        sa.Column("communication_mode", sa.String(length=32), nullable=False, server_default="IN_APP"),
    )
    op.add_column("leads", sa.Column("created_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_leads_created_by_agent_id_users",
        "leads",
        "users",
        ["created_by_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_leads_created_by_agent_id", "leads", ["created_by_agent_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_leads_created_by_agent_id", table_name="leads")
    op.drop_constraint("fk_leads_created_by_agent_id_users", "leads", type_="foreignkey")
    op.drop_column("leads", "created_by_agent_id")
    op.drop_column("leads", "communication_mode")
    op.drop_column("leads", "external_property_name")
    op.drop_column("leads", "external_owner_email")
    op.drop_column("leads", "external_owner_phone")
    op.drop_column("leads", "external_owner_name")
