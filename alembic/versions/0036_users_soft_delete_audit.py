"""Add users.deleted_at and users.deleted_by for soft-delete audit.

Revision ID: 0036_users_soft_delete_audit
Revises: 0035_merge_0034_heads
Create Date: 2026-04-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0036_users_soft_delete_audit"
down_revision: Union[str, Sequence[str], None] = "0035_merge_0034_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_deleted_by_users",
        "users",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index("ix_users_deleted_by", "users", ["deleted_by"])


def downgrade() -> None:
    op.drop_index("ix_users_deleted_by", table_name="users")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
