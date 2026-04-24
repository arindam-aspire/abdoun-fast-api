"""create property listing submissions table and additive property fields

Revision ID: 0028_prop_listing_subs
Revises: 0027_recently_viewed_properties
Create Date: 2026-04-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0028_prop_listing_subs"
down_revision: Union[str, None] = "0027_recently_viewed_properties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.create_table(
        "property_listing_submissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "current_step",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "last_completed_step",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "step_completion",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "terms_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "privacy_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "public_display_authorized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "fees_acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties_normalized.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_property_listing_submissions_submitted_by",
        "property_listing_submissions",
        ["submitted_by"],
        unique=False,
    )
    op.create_index(
        "ix_property_listing_submissions_property_id",
        "property_listing_submissions",
        ["property_id"],
        unique=False,
    )
    op.create_index(
        "ix_property_listing_submissions_status",
        "property_listing_submissions",
        ["status"],
        unique=False,
    )

    op.add_column("properties_normalized", sa.Column("listing_purpose", sa.String(length=20), nullable=True))
    op.add_column("properties_normalized", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("properties_normalized", sa.Column("parking_spaces", sa.Integer(), nullable=True))
    op.add_column("properties_normalized", sa.Column("total_floors", sa.Integer(), nullable=True))
    op.add_column("properties_normalized", sa.Column("completion_status", sa.String(length=50), nullable=True))
    op.add_column("properties_normalized", sa.Column("occupancy", sa.String(length=50), nullable=True))
    op.add_column("properties_normalized", sa.Column("ownership_type", sa.String(length=50), nullable=True))
    op.add_column("properties_normalized", sa.Column("permit_number", sa.String(length=100), nullable=True))
    op.add_column("properties_normalized", sa.Column("orientation", sa.String(length=50), nullable=True))
    op.add_column("properties_normalized", sa.Column("service_charge", sa.Numeric(15, 2), nullable=True))
    op.add_column("properties_normalized", sa.Column("maintenance_fee", sa.Numeric(15, 2), nullable=True))
    op.add_column("properties_normalized", sa.Column("youtube_url", sa.Text(), nullable=True))
    op.add_column("properties_normalized", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_properties_normalized_created_by_users",
        "properties_normalized",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_properties_normalized_created_by",
        "properties_normalized",
        ["created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_properties_normalized_created_by", table_name="properties_normalized")
    op.drop_constraint("fk_properties_normalized_created_by_users", "properties_normalized", type_="foreignkey")
    op.drop_column("properties_normalized", "created_by")
    op.drop_column("properties_normalized", "youtube_url")
    op.drop_column("properties_normalized", "maintenance_fee")
    op.drop_column("properties_normalized", "service_charge")
    op.drop_column("properties_normalized", "orientation")
    op.drop_column("properties_normalized", "permit_number")
    op.drop_column("properties_normalized", "ownership_type")
    op.drop_column("properties_normalized", "occupancy")
    op.drop_column("properties_normalized", "completion_status")
    op.drop_column("properties_normalized", "total_floors")
    op.drop_column("properties_normalized", "parking_spaces")
    op.drop_column("properties_normalized", "address")
    op.drop_column("properties_normalized", "listing_purpose")

    op.drop_index("ix_property_listing_submissions_status", table_name="property_listing_submissions")
    op.drop_index("ix_property_listing_submissions_property_id", table_name="property_listing_submissions")
    op.drop_index("ix_property_listing_submissions_submitted_by", table_name="property_listing_submissions")
    op.drop_table("property_listing_submissions")
