"""Add DB-backed property workflow options and primary-image uniqueness.

Revision ID: 0068_property_creation_uat
Revises: 0067_route_through_agency
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0068_property_creation_uat"
down_revision = "0067_route_through_agency"
branch_labels = None
depends_on = None


OPTION_VALUES = (
    ("furnishing_status", "Furnished", "furnished", None, 0),
    ("furnishing_status", "Unfurnished", "unfurnished", None, 1),
    ("furnishing_status", "Semi-Furnished", "semi-furnished", None, 2),
    ("listing_purpose", "Sale", "sale", None, 0),
    ("listing_purpose", "Rent", "rent", None, 1),
    ("listing_purpose", "Sale + Rent", "sale-or-rent", None, 2),
    ("completion_status", "Primary", "primary", None, 0),
    ("completion_status", "Secondary", "secondary", None, 1),
    ("direction", "North", "north", None, 0),
    ("direction", "Northeast", "northeast", None, 1),
    ("direction", "East", "east", None, 2),
    ("direction", "Southeast", "southeast", None, 3),
    ("direction", "South", "south", None, 4),
    ("direction", "Southwest", "southwest", None, 5),
    ("direction", "West", "west", None, 6),
    ("direction", "Northwest", "northwest", None, 7),
)

FLOOR_NAMES = (
    "Ground",
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
    "Thirteenth",
    "Fourteenth",
    "Fifteenth",
    "Sixteenth",
    "Seventeenth",
    "Eighteenth",
    "Nineteenth",
    "Twentieth",
)


def upgrade() -> None:
    op.create_table(
        "property_option_values",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("numeric_value", sa.Integer(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("group_key", "slug", name="uq_property_option_group_slug"),
    )
    op.create_index(
        "ix_property_option_values_group_active_order",
        "property_option_values",
        ["group_key", "is_active", "display_order"],
    )

    option_table = sa.table(
        "property_option_values",
        sa.column("group_key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("numeric_value", sa.Integer()),
        sa.column("display_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    rows = [
        {
            "group_key": group_key,
            "name": name,
            "slug": slug,
            "numeric_value": numeric_value,
            "display_order": display_order,
            "is_active": True,
        }
        for group_key, name, slug, numeric_value, display_order in OPTION_VALUES
    ]
    rows.extend(
        {
            "group_key": "floor",
            "name": FLOOR_NAMES[number] if number < len(FLOOR_NAMES) else f"Floor {number}",
            "slug": "ground" if number == 0 else str(number),
            "numeric_value": number,
            "display_order": number,
            "is_active": True,
        }
        for number in range(0, 51)
    )
    op.bulk_insert(option_table, rows)

    # Keep the earliest selected image primary before enforcing one primary image.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY property_id
                       ORDER BY display_order NULLS LAST, id
                   ) AS primary_rank
            FROM property_media
            WHERE media_type = 'image' AND is_primary IS TRUE
        )
        UPDATE property_media AS media
        SET is_primary = false
        FROM ranked
        WHERE media.id = ranked.id AND ranked.primary_rank > 1
        """
    )
    op.create_index(
        "uq_property_media_primary_image",
        "property_media",
        ["property_id"],
        unique=True,
        postgresql_where=sa.text("media_type = 'image' AND is_primary IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_property_media_primary_image", table_name="property_media")
    op.drop_index("ix_property_option_values_group_active_order", table_name="property_option_values")
    op.drop_table("property_option_values")
