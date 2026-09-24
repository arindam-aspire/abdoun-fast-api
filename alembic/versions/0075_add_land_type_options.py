"""Add Land Type master-data options and submission FK.

Revision ID: 0075_land_type_options
Revises: 0073_taxonomy_parking
Create Date: 2026-09-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0075_land_type_options"
down_revision = "0073_taxonomy_parking"
branch_labels = None
depends_on = None


LAND_TYPE_OPTIONS = (
    ("طوابق وشقق/دوبلكس", "floors-apartments-duplex", 0),
    ("تسويه/دوبلكس", "leveling-duplex", 1),
    ("بناء/مكاتب", "building-offices", 2),
    ("بناء/مخازن", "building-warehouses", 3),
    ("بناء/طابق الميزان", "building-mezzanine", 4),
    ("بناء/طوابق وشقق", "building-floors-apartments", 5),
    ("بناء/تسويه", "building-leveling", 6),
)


def upgrade() -> None:
    conn = op.get_bind()
    insert_sql = sa.text(
        """
        INSERT INTO property_option_values
            (group_key, name, slug, display_order, is_active, created_at, updated_at)
        VALUES
            ('land_type', :name, :slug, :display_order, true, now(), now())
        ON CONFLICT (group_key, slug) DO UPDATE
        SET name = EXCLUDED.name,
            display_order = EXCLUDED.display_order,
            is_active = true,
            updated_at = now()
        """
    )
    for name, slug, display_order in LAND_TYPE_OPTIONS:
        conn.execute(
            insert_sql,
            {"name": name, "slug": slug, "display_order": display_order},
        )

    op.add_column(
        "property_listing_submissions",
        sa.Column("land_type_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_property_listing_submissions_land_type_id",
        "property_listing_submissions",
        "property_option_values",
        ["land_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_property_listing_submissions_land_type_id",
        "property_listing_submissions",
        ["land_type_id"],
    )

    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET land_type_id = opt.id
            FROM property_option_values AS opt
            WHERE pls.land_type_id IS NULL
              AND opt.group_key = 'land_type'
              AND opt.is_active IS TRUE
              AND (
                    (
                        (pls.payload #>> '{property_details,land_type_id}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,land_type_id}')::integer
                    )
                    OR (
                        (pls.payload #>> '{property_details,landTypeId}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,landTypeId}')::integer
                    )
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET land_type_id = opt.id
            FROM property_option_values AS opt
            WHERE pls.land_type_id IS NULL
              AND opt.group_key = 'land_type'
              AND opt.is_active IS TRUE
              AND (
                    opt.name = trim(coalesce(
                        pls.payload #>> '{property_details,land_type}',
                        pls.payload #>> '{property_details,landType}'
                    ))
                    OR opt.slug = trim(both '-' from regexp_replace(
                        lower(trim(coalesce(
                            pls.payload #>> '{property_details,land_type}',
                            pls.payload #>> '{property_details,landType}'
                        ))),
                        '[^a-z0-9]+',
                        '-',
                        'g'
                    ))
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_property_listing_submissions_land_type_id", table_name="property_listing_submissions")
    op.drop_constraint(
        "fk_property_listing_submissions_land_type_id",
        "property_listing_submissions",
        type_="foreignkey",
    )
    op.drop_column("property_listing_submissions", "land_type_id")
    op.execute(
        sa.text(
            """
            DELETE FROM property_option_values
            WHERE group_key = 'land_type'
              AND slug IN (
                    'floors-apartments-duplex',
                    'leveling-duplex',
                    'building-offices',
                    'building-warehouses',
                    'building-mezzanine',
                    'building-floors-apartments',
                    'building-leveling'
              )
            """
        )
    )
