"""create user_saved_searches table

Revision ID: 0026_user_saved_searches
Revises: 0025_add_virtual_tour_url
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0026_user_saved_searches"
down_revision: Union[str, None] = "0025_add_virtual_tour_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.create_table(
        "user_saved_searches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("search_criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "notification_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "jsonb_typeof(search_criteria) = 'object'",
            name="ck_user_saved_searches_search_criteria_object",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="user_saved_searches_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="user_saved_searches_pkey"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_saved_searches_user_name"),
    )

    op.create_index(
        "idx_user_saved_searches_user_id",
        "user_saved_searches",
        ["user_id"],
    )
    op.create_index(
        "idx_user_saved_searches_search_criteria_gin",
        "user_saved_searches",
        ["search_criteria"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_user_saved_searches_search_criteria_gin", table_name="user_saved_searches")
    op.drop_index("idx_user_saved_searches_user_id", table_name="user_saved_searches")
    op.drop_table("user_saved_searches")

