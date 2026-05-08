"""Add lead lifecycle columns, history, notes, and messages.

Revision ID: 0039_lead_lifecycle
Revises: 0038_backfill_agent
Create Date: 2026-05-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0039_lead_lifecycle"
down_revision: Union[str, Sequence[str], None] = "0038_backfill_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEAD_STATUS_ENUM = postgresql.ENUM(
    "NEW",
    "IN_PROGRESS",
    "REQUEST_FOR_CLOSE",
    "CLOSED",
    name="lead_status_enum",
    create_type=False,
)
LEAD_SOURCE_ENUM = postgresql.ENUM(
    "EMAIL_FORM",
    "PHONE",
    "WHATSAPP",
    "MANUAL_ADMIN",
    name="lead_source_enum",
    create_type=False,
)
LEAD_MESSAGE_CHANNEL_ENUM = postgresql.ENUM(
    "IN_APP",
    "EMAIL",
    name="lead_message_channel_enum",
    create_type=False,
)

LEAD_STATUS_ENUM_CREATE = postgresql.ENUM("NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED", name="lead_status_enum")
LEAD_SOURCE_ENUM_CREATE = postgresql.ENUM("EMAIL_FORM", "PHONE", "WHATSAPP", "MANUAL_ADMIN", name="lead_source_enum")
LEAD_MESSAGE_CHANNEL_ENUM_CREATE = postgresql.ENUM("IN_APP", "EMAIL", name="lead_message_channel_enum")


def upgrade() -> None:
    bind = op.get_bind()
    LEAD_STATUS_ENUM_CREATE.create(bind, checkfirst=True)
    LEAD_SOURCE_ENUM_CREATE.create(bind, checkfirst=True)
    LEAD_MESSAGE_CHANNEL_ENUM_CREATE.create(bind, checkfirst=True)

    op.add_column(
        "leads",
        sa.Column("status", LEAD_STATUS_ENUM, nullable=False, server_default="NEW"),
    )
    op.add_column(
        "leads",
        sa.Column("source", LEAD_SOURCE_ENUM, nullable=False, server_default="EMAIL_FORM"),
    )
    op.add_column("leads", sa.Column("assigned_agent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("leads", sa.Column("assigned_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("leads", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("request_close_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("closed_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_leads_assigned_agent_id_users",
        "leads",
        "users",
        ["assigned_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_leads_assigned_by_admin_id_users",
        "leads",
        "users",
        ["assigned_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_leads_closed_by_admin_id_users",
        "leads",
        "users",
        ["closed_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_leads_assigned_agent_id", "leads", ["assigned_agent_id"], unique=False)
    op.create_index("ix_leads_status", "leads", ["status"], unique=False)
    op.create_index("ix_leads_source", "leads", ["source"], unique=False)
    op.create_index("ix_leads_agent_status_created", "leads", ["assigned_agent_id", "status", "created_at"], unique=False)
    op.create_index("ix_leads_source_created", "leads", ["source", "created_at"], unique=False)

    op.create_table(
        "lead_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", LEAD_STATUS_ENUM, nullable=True),
        sa.Column("to_status", LEAD_STATUS_ENUM, nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_status_history_lead_id", "lead_status_history", ["lead_id"], unique=False)
    op.create_index("ix_lead_status_history_changed_at", "lead_status_history", ["changed_at"], unique=False)
    op.create_index(
        "ix_lead_status_history_lead_changed",
        "lead_status_history",
        ["lead_id", "changed_at"],
        unique=False,
    )

    op.create_table(
        "lead_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_notes_lead_id", "lead_notes", ["lead_id"], unique=False)
    op.create_index("ix_lead_notes_created_at", "lead_notes", ["created_at"], unique=False)
    op.create_index("ix_lead_notes_lead_created", "lead_notes", ["lead_id", "created_at"], unique=False)

    op.create_table(
        "lead_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("channel", LEAD_MESSAGE_CHANNEL_ENUM, nullable=False, server_default="IN_APP"),
        sa.Column("delivery_state", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_messages_lead_id", "lead_messages", ["lead_id"], unique=False)
    op.create_index("ix_lead_messages_created_at", "lead_messages", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lead_messages_created_at", table_name="lead_messages")
    op.drop_index("ix_lead_messages_lead_id", table_name="lead_messages")
    op.drop_table("lead_messages")

    op.drop_index("ix_lead_notes_lead_created", table_name="lead_notes")
    op.drop_index("ix_lead_notes_created_at", table_name="lead_notes")
    op.drop_index("ix_lead_notes_lead_id", table_name="lead_notes")
    op.drop_table("lead_notes")

    op.drop_index("ix_lead_status_history_lead_changed", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_changed_at", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_lead_id", table_name="lead_status_history")
    op.drop_table("lead_status_history")

    op.drop_index("ix_leads_source_created", table_name="leads")
    op.drop_index("ix_leads_agent_status_created", table_name="leads")
    op.drop_index("ix_leads_source", table_name="leads")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_assigned_agent_id", table_name="leads")

    op.drop_constraint("fk_leads_closed_by_admin_id_users", "leads", type_="foreignkey")
    op.drop_constraint("fk_leads_assigned_by_admin_id_users", "leads", type_="foreignkey")
    op.drop_constraint("fk_leads_assigned_agent_id_users", "leads", type_="foreignkey")

    op.drop_column("leads", "closed_by_admin_id")
    op.drop_column("leads", "closed_at")
    op.drop_column("leads", "request_close_at")
    op.drop_column("leads", "last_activity_at")
    op.drop_column("leads", "assigned_by_admin_id")
    op.drop_column("leads", "assigned_agent_id")
    op.drop_column("leads", "source")
    op.drop_column("leads", "status")

    bind = op.get_bind()
    LEAD_MESSAGE_CHANNEL_ENUM_CREATE.drop(bind, checkfirst=True)
    LEAD_SOURCE_ENUM_CREATE.drop(bind, checkfirst=True)
    LEAD_STATUS_ENUM_CREATE.drop(bind, checkfirst=True)
