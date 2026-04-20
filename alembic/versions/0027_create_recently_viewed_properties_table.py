"""create recently viewed properties table

Revision ID: 0027_recently_viewed_properties
Revises: 0026_user_saved_searches
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0027_recently_viewed_properties"
down_revision: Union[str, None] = "0026_user_saved_searches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recently_viewed_properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties_normalized.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "property_id", name="uq_recent_views_user_property"),
    )
    op.create_index(
        "ix_recent_views_user_viewed_at_desc",
        "recently_viewed_properties",
        ["user_id", sa.text("viewed_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recent_views_user_viewed_at_desc",
        table_name="recently_viewed_properties",
    )
    op.drop_table("recently_viewed_properties")
