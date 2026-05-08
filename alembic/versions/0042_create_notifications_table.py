"""Create Phase 1 notification tables + user language.

Revision ID: 0042_create_notifications
Revises: 0041_manual_owner_leads
Create Date: 2026-05-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0042_create_notifications"
down_revision: Union[str, Sequence[str], None] = "0041_manual_owner_leads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # notifications
    # ---------------------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type_key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_notifications_recipient_user_id_users",
        "notifications",
        "users",
        ["recipient_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_notifications_actor_user_id_users",
        "notifications",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_actor_user_id", "notifications", ["actor_user_id"])
    op.create_index("ix_notifications_type_key", "notifications", ["type_key"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_archived_at", "notifications", ["archived_at"])

    # Spec-required indexes
    op.create_index("idx_notifications_recipient", "notifications", ["recipient_user_id"])
    op.create_index("idx_notifications_unread", "notifications", ["recipient_user_id", "is_read"])
    op.create_index("idx_notifications_created", "notifications", [sa.text("created_at DESC")])

    # ---------------------------------------------------------------------
    # notification_preferences
    # ---------------------------------------------------------------------
    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "notification_type", name="uq_notification_preferences_user_type"),
    )
    op.create_foreign_key(
        "fk_notification_preferences_user_id_users",
        "notification_preferences",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    # ---------------------------------------------------------------------
    # users.preferred_language
    # ---------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("preferred_language", sa.String(length=10), nullable=False, server_default="en"),
    )
    op.alter_column("users", "preferred_language", server_default=None)


def downgrade() -> None:
    # Reverse order
    op.drop_column("users", "preferred_language")

    op.drop_index("ix_notification_preferences_user_id", table_name="notification_preferences")
    op.drop_constraint(
        "fk_notification_preferences_user_id_users",
        "notification_preferences",
        type_="foreignkey",
    )
    op.drop_table("notification_preferences")

    op.drop_index("idx_notifications_created", table_name="notifications")
    op.drop_index("idx_notifications_unread", table_name="notifications")
    op.drop_index("idx_notifications_recipient", table_name="notifications")

    op.drop_index("ix_notifications_archived_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_type_key", table_name="notifications")
    op.drop_index("ix_notifications_actor_user_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")

    op.drop_constraint("fk_notifications_actor_user_id_users", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notifications_recipient_user_id_users", "notifications", type_="foreignkey")
    op.drop_table("notifications")

