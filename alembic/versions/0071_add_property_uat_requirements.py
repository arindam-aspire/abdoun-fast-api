"""Add Property UAT: sequential refs, completion statuses, requested features.

Revision ID: 0071_add_property_uat
Revises: 0070_draft_furnishing_floor
Create Date: 2026-09-15
"""

from __future__ import annotations

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0071_add_property_uat"
down_revision = "0070_draft_furnishing_floor"
branch_labels = None
depends_on = None

FEATURES_PATH = Path(__file__).resolve().parents[2] / "app" / "config" / "property_features_seed.json"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE SEQUENCE IF NOT EXISTS property_reference_number_seq
                AS bigint
                INCREMENT BY 1
                MINVALUE 1
                NO MAXVALUE
                CACHE 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            SELECT setval(
                'property_reference_number_seq',
                GREATEST(
                    10000,
                    COALESCE(
                        (
                            SELECT MAX(reference_number::bigint)
                            FROM property_listing_submissions
                            WHERE reference_number ~ '^[0-9]+$'
                        ),
                        10000
                    )
                )
            )
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO property_option_values
                (group_key, name, slug, display_order, is_active, created_at, updated_at)
            VALUES
                ('completion_status', 'Off Plan', 'off-plan', 2, true, now(), now()),
                ('completion_status', 'Ready', 'ready', 3, true, now(), now())
            ON CONFLICT (group_key, slug) DO UPDATE
            SET name = EXCLUDED.name,
                is_active = true,
                updated_at = now()
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE property_option_values
            SET is_active = false, updated_at = now()
            WHERE group_key = 'completion_status'
              AND trim(both '-' from regexp_replace(lower(trim(slug)), '[^a-z0-9]+', '-', 'g'))
                  IN ('under-construction', 'underconstruction')
            """
        )
    )

    if not FEATURES_PATH.exists():
        return

    features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    conn = op.get_bind()
    insert_sql = sa.text(
        """
        INSERT INTO features (
            name, slug, category_id, property_type_id, feature_group,
            display_order, is_active, created_at, updated_at
        )
        SELECT
            :name,
            :slug,
            category.id,
            property_type.id,
            :feature_group,
            :display_order,
            TRUE,
            now(),
            now()
        FROM property_categories AS category
        LEFT JOIN property_types AS property_type
          ON :property_type_name IS NOT NULL
         AND property_type.category_id = category.id
         AND LOWER(property_type.name) = LOWER(:property_type_name)
        WHERE LOWER(category.name) = LOWER(:category_name)
          AND NOT EXISTS (
                SELECT 1
                FROM features AS existing
                WHERE existing.slug = :slug
                   OR (
                        existing.category_id = category.id
                    AND existing.feature_group = :feature_group
                    AND LOWER(existing.name) = LOWER(:name)
                    AND (
                          (:property_type_name IS NULL AND existing.property_type_id IS NULL)
                          OR existing.property_type_id IS NOT DISTINCT FROM property_type.id
                    )
                   )
          )
        LIMIT 1
        ON CONFLICT (slug) DO NOTHING
        """
    )
    for feature in features:
        conn.execute(
            insert_sql,
            {
                "name": feature["name"],
                "slug": feature["slug"],
                "category_name": feature.get("category"),
                "property_type_name": feature.get("property_type"),
                "feature_group": feature.get("feature_group") or "FEATURE",
                "display_order": int(feature.get("display_order") or 0),
            },
        )


def downgrade() -> None:
    op.execute(sa.text("DROP SEQUENCE IF EXISTS property_reference_number_seq"))
