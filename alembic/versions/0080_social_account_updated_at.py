"""Ensure social provider identity mapping can record updates.

The live database already has `social_accounts`. This migration creates that
table only when it is missing, then adds `updated_at` and the provider
identity unique constraint when they are missing.

Revision ID: 0080_social_account_updated_at
Revises: 0079_phone_otp_attempts
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0080_social_account_updated_at"
down_revision = "0079_phone_otp_attempts"
branch_labels = None
depends_on = None


def _table_names(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _unique_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "social_accounts" not in _table_names(inspector):
        op.create_table(
            "social_accounts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("provider_user_id", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint(
                "provider",
                "provider_user_id",
                name="uq_social_accounts_provider_provider_user_id",
            ),
        )
        op.create_index("ix_social_accounts_user_id", "social_accounts", ["user_id"])
        return

    if "updated_at" not in _column_names(inspector, "social_accounts"):
        op.add_column(
            "social_accounts",
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    if "ix_social_accounts_user_id" not in _index_names(inspector, "social_accounts"):
        op.create_index("ix_social_accounts_user_id", "social_accounts", ["user_id"])
    if "uq_social_accounts_provider_provider_user_id" not in _unique_names(inspector, "social_accounts"):
        if "uq_social_accounts_provider_provider_user_id" not in _index_names(inspector, "social_accounts"):
            op.create_unique_constraint(
                "uq_social_accounts_provider_provider_user_id",
                "social_accounts",
                ["provider", "provider_user_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "social_accounts" not in _table_names(inspector):
        return
    if "updated_at" in _column_names(inspector, "social_accounts"):
        op.drop_column("social_accounts", "updated_at")
