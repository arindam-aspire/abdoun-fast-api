"""add indexed property_hash to properties_normalized

Revision ID: 0022_add_property_hash_index
Revises: 0021_users_phone_number_nullable
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_add_property_hash_index"
down_revision = "0021_phone_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Needed for digest() in backfill expression.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.add_column(
        "properties_normalized",
        sa.Column("property_hash", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_properties_normalized_property_hash",
        "properties_normalized",
        ["property_hash"],
    )

    # Backfill using SHA256(UUID text), first 8 bytes interpreted as big-endian integer, mod 1e9.
    # This matches app.schemas.property.uuid_to_int_hash().
    op.execute(
        """
        UPDATE properties_normalized
        SET property_hash = (
          (
            (get_byte(d,0)::bigint << 56) +
            (get_byte(d,1)::bigint << 48) +
            (get_byte(d,2)::bigint << 40) +
            (get_byte(d,3)::bigint << 32) +
            (get_byte(d,4)::bigint << 24) +
            (get_byte(d,5)::bigint << 16) +
            (get_byte(d,6)::bigint << 8)  +
            (get_byte(d,7)::bigint)
          ) % 1000000000
        )
        FROM (
          SELECT id, digest(id::text, 'sha256') AS d
          FROM properties_normalized
          WHERE property_hash IS NULL
        ) s
        WHERE properties_normalized.id = s.id;
        """
    )

    op.alter_column("properties_normalized", "property_hash", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_properties_normalized_property_hash", table_name="properties_normalized")
    op.drop_column("properties_normalized", "property_hash")
