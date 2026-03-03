"""create property_media table and backfill images

Revision ID: 0013_property_media
Revises: 0012_translation_address
Create Date: 2026-03-02

Adds normalized media table and migrates legacy properties_normalized.images JSON array
into property_media rows (media_type='image').
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_property_media"
down_revision = "0012_translation_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_media",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("properties_normalized.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumb_url", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint(
            "media_type IN ('image', 'video', 'floor_plan', 'document')",
            name="ck_property_media_media_type",
        ),
    )
    op.create_index("idx_property_media_property_id", "property_media", ["property_id"], unique=False)
    op.create_index(
        "idx_property_media_property_type_order",
        "property_media",
        ["property_id", "media_type", "display_order"],
        unique=False,
    )

    # Backfill legacy images JSON array into property_media rows.
    op.execute(
        """
        INSERT INTO property_media (
            property_id,
            media_type,
            url,
            thumb_url,
            is_primary,
            display_order,
            caption
        )
        SELECT
            p.id AS property_id,
            'image' AS media_type,
            j.value AS url,
            j.value AS thumb_url,
            (j.ord = 1) AS is_primary,
            j.ord AS display_order,
            NULL AS caption
        FROM properties_normalized p
        CROSS JOIN LATERAL json_array_elements_text(
            CASE
                WHEN p.images IS NULL OR btrim(p.images) = '' THEN '[]'::json
                ELSE p.images::json
            END
        ) WITH ORDINALITY AS j(value, ord)
        """
    )


def downgrade() -> None:
    op.drop_index("idx_property_media_property_type_order", table_name="property_media")
    op.drop_index("idx_property_media_property_id", table_name="property_media")
    op.drop_table("property_media")
