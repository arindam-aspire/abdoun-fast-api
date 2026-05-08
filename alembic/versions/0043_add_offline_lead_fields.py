"""Add offline lead fields.

Revision ID: 0043_offline_leads
Revises: 0042_create_notifications
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0043_offline_leads"
down_revision: Union[str, Sequence[str], None] = "0042_create_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE lead_source_enum ADD VALUE IF NOT EXISTS 'OFFLINE_MANUAL'")

    op.add_column("leads", sa.Column("offline_inquiry_type", sa.String(length=64), nullable=True))
    op.add_column("leads", sa.Column("offline_source", sa.String(length=64), nullable=True))
    op.add_column("leads", sa.Column("offline_notes", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_leads_created_by_admin_id_users",
        "leads",
        "users",
        ["created_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_leads_created_by_admin_id", "leads", ["created_by_admin_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_leads_created_by_admin_id", table_name="leads")
    op.drop_constraint("fk_leads_created_by_admin_id_users", "leads", type_="foreignkey")
    op.drop_column("leads", "created_by_admin_id")
    op.drop_column("leads", "offline_notes")
    op.drop_column("leads", "offline_source")
    op.drop_column("leads", "offline_inquiry_type")
