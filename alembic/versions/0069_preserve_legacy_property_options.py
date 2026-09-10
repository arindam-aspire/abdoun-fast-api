"""Preserve legacy JSON option values in the new master-data catalog.

Revision ID: 0069_legacy_property_options
Revises: 0068_property_creation_uat
Create Date: 2026-09-09
"""

from alembic import op


revision = "0069_legacy_property_options"
down_revision = "0068_property_creation_uat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing submissions used free-form JSON values. Register those values so
    # an unchanged legacy draft can still be saved or submitted.
    for group_key, expression in (
        (
            "furnishing_status",
            "coalesce(payload #>> '{property_details,furnishing}', "
            "payload #>> '{property_details,furnishing_status}', "
            "payload #>> '{property_details,furniture_status}')",
        ),
        ("completion_status", "payload #>> '{property_details,completion_status}'"),
        ("direction", "payload #>> '{property_details,direction}'"),
        ("listing_purpose", "payload #>> '{basic_information,listing_purpose}'"),
    ):
        op.execute(
            f"""
            INSERT INTO property_option_values
                (group_key, name, slug, display_order, is_active, created_at, updated_at)
            SELECT DISTINCT
                '{group_key}',
                trim({expression}),
                trim(both '-' from regexp_replace(lower(trim({expression})), '[^a-z0-9]+', '-', 'g')),
                1000,
                true,
                now(),
                now()
            FROM property_listing_submissions
            WHERE nullif(trim({expression}), '') IS NOT NULL
            ON CONFLICT (group_key, slug) DO NOTHING
            """
        )

    op.execute(
        """
        INSERT INTO property_option_values
            (group_key, name, slug, numeric_value, display_order, is_active, created_at, updated_at)
        SELECT DISTINCT
            'floor',
            'Floor ' || floor_number,
            floor_number,
            floor_number::integer,
            floor_number::integer,
            true,
            now(),
            now()
        FROM (
            SELECT payload #>> '{property_details,floor_number}' AS floor_number
            FROM property_listing_submissions
        ) legacy
        WHERE floor_number ~ '^[0-9]+$'
        ON CONFLICT (group_key, slug) DO NOTHING
        """
    )


def downgrade() -> None:
    # Legacy-derived rows are intentionally retained: deleting them could make
    # pre-existing submissions invalid after a rollback/upgrade cycle.
    pass
