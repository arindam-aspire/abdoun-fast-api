"""create owner and property_owner tables

Revision ID: 0023_owner_and_property_owner
Revises: 0022_add_property_hash_index
Create Date: 2026-04-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0023_owner_and_property_owner"
down_revision: Union[str, None] = "0022_add_property_hash_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "owner",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("nationality", sa.String(length=100), nullable=True),
        sa.Column("ssi", sa.String(length=50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "documents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.create_index("ix_owner_email", "owner", ["email"])

    op.create_table(
        "property_owner",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.ForeignKeyConstraint(["owner_id"], ["owner.owner_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties_normalized.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "owner_id", name="uq_property_owner_property_owner"),
    )
    op.create_index("ix_property_owner_owner_id", "property_owner", ["owner_id"])
    op.create_index("ix_property_owner_property_id", "property_owner", ["property_id"])


def downgrade() -> None:
    op.drop_index("ix_property_owner_property_id", table_name="property_owner")
    op.drop_index("ix_property_owner_owner_id", table_name="property_owner")
    op.drop_table("property_owner")
    op.drop_index("ix_owner_email", table_name="owner")
    op.drop_table("owner")
