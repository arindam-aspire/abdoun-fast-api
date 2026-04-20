"""create user_property_favorites table

Revision ID: 0024_user_property_favorites
Revises: 0023_owner_and_property_owner
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0024_user_property_favorites"
down_revision: Union[str, None] = "0023_owner_and_property_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.create_table(
        "user_property_favorites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="user_property_favorites_user_id_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties_normalized.id"],
            name="user_property_favorites_property_id_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="user_property_favorites_pkey"),
        sa.UniqueConstraint(
            "user_id",
            "property_id",
            name="user_property_favorites_unique",
        ),
    )

    op.create_index(
        "idx_user_favorites_user_id",
        "user_property_favorites",
        ["user_id"],
    )
    op.create_index(
        "idx_user_favorites_property_id",
        "user_property_favorites",
        ["property_id"],
    )
    op.create_index(
        "idx_user_favorites_user_property",
        "user_property_favorites",
        ["user_id", "property_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_favorites_user_property", table_name="user_property_favorites")
    op.drop_index("idx_user_favorites_property_id", table_name="user_property_favorites")
    op.drop_index("idx_user_favorites_user_id", table_name="user_property_favorites")
    op.drop_table("user_property_favorites")

