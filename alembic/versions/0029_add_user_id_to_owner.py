"""add user_id fk column to owner

Revision ID: 0029_owner_user_id
Revises: 0028_prop_listing_subs
Create Date: 2026-04-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0029_owner_user_id"
down_revision: Union[str, None] = "0028_prop_listing_subs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("owner", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_owner_user_id_users",
        "owner",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_owner_user_id", "owner", ["user_id"], unique=False)
    op.create_index("ix_owner_phone", "owner", ["phone"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_owner_phone", table_name="owner")
    op.drop_index("ix_owner_user_id", table_name="owner")
    op.drop_constraint("fk_owner_user_id_users", "owner", type_="foreignkey")
    op.drop_column("owner", "user_id")
