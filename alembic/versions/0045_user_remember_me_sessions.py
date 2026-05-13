"""Create user_remember_me_sessions for Remember Me persistent auth.

Revision ID: 0045_user_remember_me_sessions
Revises: 0044_notification_idempotency
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0045_user_remember_me_sessions"
down_revision: Union[str, Sequence[str], None] = "0044_notification_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_remember_me_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("cognito_refresh_encrypted", sa.Text(), nullable=False),
        sa.Column("cognito_username", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_remember_me_sessions_user_id",
        "user_remember_me_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_remember_me_sessions_expires_at",
        "user_remember_me_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_remember_me_sessions_token_hash",
        "user_remember_me_sessions",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_remember_me_sessions_token_hash", table_name="user_remember_me_sessions")
    op.drop_index("ix_user_remember_me_sessions_expires_at", table_name="user_remember_me_sessions")
    op.drop_index("ix_user_remember_me_sessions_user_id", table_name="user_remember_me_sessions")
    op.drop_table("user_remember_me_sessions")
