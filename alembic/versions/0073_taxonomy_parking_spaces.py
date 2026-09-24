"""Add taxonomy grouping and convert parking space from dropdown to a count.

Revision ID: 0073_taxonomy_parking
Revises: 0072_dls_locations
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0073_taxonomy_parking"
down_revision = "0072_dls_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("property_categories", sa.Column("group_slug", sa.String(length=50), nullable=True))
    op.add_column("property_categories", sa.Column("group_name", sa.String(length=100), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE property_categories
            SET group_slug = CASE
                    WHEN slug = 'land' THEN 'land'
                    ELSE 'properties'
                END,
                group_name = CASE
                    WHEN slug = 'land' THEN 'Land'
                    ELSE 'Properties'
                END,
                updated_at = now()
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_option_values
            SET is_active = false, updated_at = now()
            WHERE group_key IN ('parking', 'parking_space', 'parking_spaces')
              AND is_active IS TRUE
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions
            SET payload = jsonb_set(
                    payload,
                    '{property_details,parking_spaces}',
                    to_jsonb(
                        (
                            regexp_replace(
                                coalesce(
                                    payload #>> '{property_details,parking_spaces}',
                                    payload #>> '{property_details,parking_space}',
                                    payload #>> '{property_details,parkingSpaces}',
                                    payload #>> '{property_details,parkingSpace}',
                                    payload #>> '{property_details,parking}',
                                    ''
                                ),
                                '[^0-9]',
                                '',
                                'g'
                            )
                        )::integer
                    ),
                    true
                ),
                updated_at = now()
            WHERE deleted_at IS NULL
              AND coalesce(
                    payload #>> '{property_details,parking_spaces}',
                    payload #>> '{property_details,parking_space}',
                    payload #>> '{property_details,parkingSpaces}',
                    payload #>> '{property_details,parkingSpace}',
                    payload #>> '{property_details,parking}'
                ) ~ '[0-9]'
              AND regexp_replace(
                    coalesce(
                        payload #>> '{property_details,parking_spaces}',
                        payload #>> '{property_details,parking_space}',
                        payload #>> '{property_details,parkingSpaces}',
                        payload #>> '{property_details,parkingSpace}',
                        payload #>> '{property_details,parking}',
                        ''
                    ),
                    '[^0-9]',
                    '',
                    'g'
                ) ~ '^[0-9]+$'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("property_categories", "group_name")
    op.drop_column("property_categories", "group_slug")
