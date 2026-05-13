"""Add password login failed-attempt lockout columns on users.

Revision ID: 0046_password_login_lockout
Revises: 0045_user_remember_me_sessions
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0046_password_login_lockout"
down_revision: Union[str, Sequence[str], None] = "0045_user_remember_me_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_login_failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("password_login_first_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_login_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_password_login_locked_until",
        "users",
        ["password_login_locked_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_password_login_locked_until", table_name="users")
    op.drop_column("users", "password_login_locked_until")
    op.drop_column("users", "password_login_first_failed_at")
    op.drop_column("users", "password_login_failed_attempts")
