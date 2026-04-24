"""add review fields to property listing submissions

Revision ID: 0030_subm_review_fields
Revises: 0029_owner_user_id
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0030_subm_review_fields"
down_revision: Union[str, None] = "0029_owner_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "property_listing_submissions",
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "property_listing_submissions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "property_listing_submissions",
        sa.Column("review_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_property_listing_submissions_reviewed_by_users",
        "property_listing_submissions",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_property_listing_submissions_reviewed_by",
        "property_listing_submissions",
        ["reviewed_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_property_listing_submissions_reviewed_by",
        table_name="property_listing_submissions",
    )
    op.drop_constraint(
        "fk_property_listing_submissions_reviewed_by_users",
        "property_listing_submissions",
        type_="foreignkey",
    )
    op.drop_column("property_listing_submissions", "review_reason")
    op.drop_column("property_listing_submissions", "reviewed_at")
    op.drop_column("property_listing_submissions", "reviewed_by")
