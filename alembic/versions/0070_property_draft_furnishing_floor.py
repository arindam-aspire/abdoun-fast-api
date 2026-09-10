"""Persist furnishing status and floor on property drafts.

Revision ID: 0070_draft_furnishing_floor
Revises: 0069_legacy_property_options
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0070_draft_furnishing_floor"
down_revision = "0069_legacy_property_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_listing_submissions",
        sa.Column("furnishing_status_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "property_listing_submissions",
        sa.Column("floor_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_property_listing_submissions_furnishing_status_id",
        "property_listing_submissions",
        "property_option_values",
        ["furnishing_status_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_property_listing_submissions_floor_id",
        "property_listing_submissions",
        "property_option_values",
        ["floor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_property_listing_submissions_furnishing_status_id",
        "property_listing_submissions",
        ["furnishing_status_id"],
    )
    op.create_index(
        "ix_property_listing_submissions_floor_id",
        "property_listing_submissions",
        ["floor_id"],
    )

    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET furnishing_status_id = opt.id
            FROM property_option_values AS opt
            WHERE pls.furnishing_status_id IS NULL
              AND opt.group_key = 'furnishing_status'
              AND opt.is_active IS TRUE
              AND (
                    (
                        (pls.payload #>> '{property_details,furnishing_status_id}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,furnishing_status_id}')::integer
                    )
                    OR (
                        (pls.payload #>> '{property_details,furnishingStatusId}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,furnishingStatusId}')::integer
                    )
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET furnishing_status_id = opt.id
            FROM property_option_values AS opt
            WHERE pls.furnishing_status_id IS NULL
              AND opt.group_key = 'furnishing_status'
              AND opt.is_active IS TRUE
              AND trim(both '-' from regexp_replace(
                    lower(trim(coalesce(
                        pls.payload #>> '{property_details,furnishing}',
                        pls.payload #>> '{property_details,furnishing_status}',
                        pls.payload #>> '{property_details,furniture_status}',
                        pls.payload #>> '{property_details,furnishingStatus}'
                    ))),
                    '[^a-z0-9]+',
                    '-',
                    'g'
              )) = opt.slug
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET floor_id = opt.id
            FROM property_option_values AS opt
            WHERE pls.floor_id IS NULL
              AND opt.group_key = 'floor'
              AND opt.is_active IS TRUE
              AND (
                    (
                        (pls.payload #>> '{property_details,floor_id}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,floor_id}')::integer
                    )
                    OR (
                        (pls.payload #>> '{property_details,floorId}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,floorId}')::integer
                    )
                    OR (
                        (pls.payload #>> '{property_details,floor}') ~ '^[0-9]+$'
                        AND opt.id = (pls.payload #>> '{property_details,floor}')::integer
                    )
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET floor_id = opt.id
            FROM property_option_values AS opt
            WHERE pls.floor_id IS NULL
              AND opt.group_key = 'floor'
              AND opt.is_active IS TRUE
              AND (
                    (
                        (pls.payload #>> '{property_details,floor_number}') ~ '^[0-9]+$'
                        AND opt.numeric_value = (pls.payload #>> '{property_details,floor_number}')::integer
                    )
                    OR lower(opt.name) = lower(trim(coalesce(
                        pls.payload #>> '{property_details,floor_level}',
                        pls.payload #>> '{property_details,floorLevel}',
                        pls.payload #>> '{property_details,floor}'
                    )))
                    OR opt.slug = trim(both '-' from regexp_replace(
                        lower(trim(coalesce(
                            pls.payload #>> '{property_details,floor_level}',
                            pls.payload #>> '{property_details,floorLevel}',
                            pls.payload #>> '{property_details,floor}'
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
    op.drop_index("ix_property_listing_submissions_floor_id", table_name="property_listing_submissions")
    op.drop_index("ix_property_listing_submissions_furnishing_status_id", table_name="property_listing_submissions")
    op.drop_constraint("fk_property_listing_submissions_floor_id", "property_listing_submissions", type_="foreignkey")
    op.drop_constraint(
        "fk_property_listing_submissions_furnishing_status_id",
        "property_listing_submissions",
        type_="foreignkey",
    )
    op.drop_column("property_listing_submissions", "floor_id")
    op.drop_column("property_listing_submissions", "furnishing_status_id")
