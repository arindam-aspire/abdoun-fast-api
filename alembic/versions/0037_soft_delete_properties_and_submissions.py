"""Add soft-delete audit fields to properties and submissions.

Revision ID: 0037_soft_delete_props
Revises: 0036_users_soft_delete_audit
Create Date: 2026-04-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0037_soft_delete_props"
down_revision: Union[str, Sequence[str], None] = "0036_users_soft_delete_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # property_listing_submissions soft delete
    op.add_column(
        "property_listing_submissions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "property_listing_submissions",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "property_listing_submissions",
        sa.Column("delete_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_property_listing_submissions_deleted_by_users",
        "property_listing_submissions",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_property_listing_submissions_deleted_at",
        "property_listing_submissions",
        ["deleted_at"],
    )
    op.create_index(
        "ix_property_listing_submissions_deleted_by",
        "property_listing_submissions",
        ["deleted_by"],
    )

    # properties_normalized soft delete
    op.add_column(
        "properties_normalized",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("delete_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_properties_normalized_deleted_by_users",
        "properties_normalized",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_properties_normalized_deleted_at", "properties_normalized", ["deleted_at"])
    op.create_index("ix_properties_normalized_deleted_by", "properties_normalized", ["deleted_by"])


def downgrade() -> None:
    op.drop_index("ix_properties_normalized_deleted_by", table_name="properties_normalized")
    op.drop_index("ix_properties_normalized_deleted_at", table_name="properties_normalized")
    op.drop_constraint("fk_properties_normalized_deleted_by_users", "properties_normalized", type_="foreignkey")
    op.drop_column("properties_normalized", "delete_reason")
    op.drop_column("properties_normalized", "deleted_by")
    op.drop_column("properties_normalized", "deleted_at")

    op.drop_index("ix_property_listing_submissions_deleted_by", table_name="property_listing_submissions")
    op.drop_index("ix_property_listing_submissions_deleted_at", table_name="property_listing_submissions")
    op.drop_constraint(
        "fk_property_listing_submissions_deleted_by_users",
        "property_listing_submissions",
        type_="foreignkey",
    )
    op.drop_column("property_listing_submissions", "delete_reason")
    op.drop_column("property_listing_submissions", "deleted_by")
    op.drop_column("property_listing_submissions", "deleted_at")

