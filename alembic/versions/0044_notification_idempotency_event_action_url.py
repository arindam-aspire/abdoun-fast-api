"""Add notification idempotency, event_type, action_url.

Revision ID: 0044_notification_idempotency
Revises: 0043_offline_leads
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0044_notification_idempotency"
down_revision: Union[str, Sequence[str], None] = "0043_offline_leads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("notifications", sa.Column("event_type", sa.String(length=100), nullable=True))
    op.add_column("notifications", sa.Column("action_url", sa.Text(), nullable=True))

    op.execute("UPDATE notifications SET event_type = type_key WHERE event_type IS NULL")

    # PostgreSQL: multiple NULLs do not violate UNIQUE.
    op.create_index(
        "uq_notifications_idempotency",
        "notifications",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index("ix_notifications_event_type", "notifications", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_notifications_event_type", table_name="notifications")
    op.drop_index("uq_notifications_idempotency", table_name="notifications")
    op.drop_column("notifications", "action_url")
    op.drop_column("notifications", "event_type")
    op.drop_column("notifications", "idempotency_key")
