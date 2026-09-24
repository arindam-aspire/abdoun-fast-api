"""Backup and regenerate property reference numbers as prefix + global sequence.

Revision ID: 0077_prefixed_property_refs
Revises: 0076_prefer_dls_records
Create Date: 2026-09-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0077_prefixed_property_refs"
down_revision = "0076_prefer_dls_records"
branch_labels = None
depends_on = None

BACKUP_TABLE = "property_listing_submissions_reference_number_backup"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
                submission_id UUID PRIMARY KEY,
                previous_reference_number VARCHAR(128),
                previous_payload_reference_number TEXT,
                backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO {BACKUP_TABLE} (
                submission_id,
                previous_reference_number,
                previous_payload_reference_number
            )
            SELECT
                id,
                reference_number,
                nullif(btrim(payload #>> '{{property_details,reference_number}}'), '')
            FROM property_listing_submissions
            ON CONFLICT (submission_id) DO NOTHING
            """
        )
    )
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
            CREATE UNIQUE INDEX IF NOT EXISTS uq_property_listing_submissions_reference_number
            ON property_listing_submissions (reference_number)
            WHERE reference_number IS NOT NULL
            """
        )
    )
    # Clear assigned values first so unique index cannot collide mid-rewrite.
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions
            SET reference_number = NULL,
                payload = CASE
                    WHEN payload ? 'property_details'
                     AND jsonb_typeof(payload -> 'property_details') = 'object'
                    THEN payload #- '{property_details,reference_number}'
                    ELSE payload
                END
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH source AS (
                SELECT
                    pls.id,
                    pls.created_at,
                    CASE
                        WHEN nullif(btrim(pls.payload #>> '{basic_information,category_id}'), '') ~ '^[0-9]+$'
                        THEN btrim(pls.payload #>> '{basic_information,category_id}')::int
                    END AS category_id,
                    CASE
                        WHEN nullif(btrim(pls.payload #>> '{basic_information,type_id}'), '') ~ '^[0-9]+$'
                        THEN btrim(pls.payload #>> '{basic_information,type_id}')::int
                    END AS type_id,
                    nullif(lower(btrim(coalesce(
                        pls.payload #>> '{basic_information,category_slug}',
                        pls.payload #>> '{basic_information,category}'
                    ))), '') AS category_slug,
                    nullif(lower(btrim(coalesce(
                        pls.payload #>> '{basic_information,type_slug}',
                        pls.payload #>> '{basic_information,property_type}',
                        pls.payload #>> '{basic_information,type}'
                    ))), '') AS type_slug
                FROM property_listing_submissions AS pls
            ),
            resolved AS (
                SELECT
                    source.id,
                    source.created_at,
                    coalesce(pc_by_id.name, pc_by_slug.name, source.category_slug) AS category_label,
                    coalesce(pt_by_id.name, pt_by_slug.name, replace(source.type_slug, '-', ' ')) AS type_label
                FROM source
                LEFT JOIN property_categories AS pc_by_id
                  ON source.category_id IS NOT NULL
                 AND pc_by_id.id = source.category_id
                LEFT JOIN property_categories AS pc_by_slug
                  ON source.category_id IS NULL
                 AND source.category_slug IS NOT NULL
                 AND lower(pc_by_slug.slug) = source.category_slug
                LEFT JOIN property_types AS pt_by_id
                  ON source.type_id IS NOT NULL
                 AND pt_by_id.id = source.type_id
                LEFT JOIN property_types AS pt_by_slug
                  ON source.type_id IS NULL
                 AND source.type_slug IS NOT NULL
                 AND lower(pt_by_slug.slug) = source.type_slug
                 AND (
                        coalesce(pc_by_id.id, pc_by_slug.id) IS NULL
                     OR pt_by_slug.category_id = coalesce(pc_by_id.id, pc_by_slug.id)
                 )
            ),
            prefixed AS (
                SELECT
                    id,
                    created_at,
                    upper(substr(regexp_replace(coalesce(category_label, ''), '[^A-Za-z]', '', 'g'), 1, 1)) AS category_prefix,
                    upper(
                        regexp_replace(
                            initcap(regexp_replace(coalesce(type_label, ''), '[^A-Za-z]+', ' ', 'g')),
                            '[^A-Z]',
                            '',
                            'g'
                        )
                    ) AS type_prefix
                FROM resolved
            ),
            numbered AS (
                SELECT
                    id,
                    category_prefix || type_prefix AS prefix,
                    row_number() OVER (ORDER BY created_at ASC NULLS LAST, id ASC) AS seq
                FROM prefixed
                WHERE category_prefix <> ''
                  AND type_prefix <> ''
            )
            UPDATE property_listing_submissions AS pls
            SET
                reference_number = numbered.prefix
                    || CASE
                        WHEN numbered.seq < 10000 THEN lpad(numbered.seq::text, 4, '0')
                        ELSE numbered.seq::text
                    END,
                payload = CASE
                    WHEN pls.payload ? 'property_details'
                     AND jsonb_typeof(pls.payload -> 'property_details') = 'object'
                    THEN jsonb_set(
                        pls.payload,
                        '{property_details,reference_number}',
                        to_jsonb(
                            numbered.prefix
                            || CASE
                                WHEN numbered.seq < 10000 THEN lpad(numbered.seq::text, 4, '0')
                                ELSE numbered.seq::text
                            END
                        ),
                        true
                    )
                    ELSE pls.payload
                END
            FROM numbered
            WHERE pls.id = numbered.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            SELECT setval(
                'property_reference_number_seq',
                GREATEST(
                    1,
                    COALESCE(
                        (
                            SELECT COUNT(*)::bigint
                            FROM property_listing_submissions
                            WHERE reference_number IS NOT NULL
                        ),
                        0
                    )
                ),
                COALESCE(
                    (
                        SELECT COUNT(*)::bigint
                        FROM property_listing_submissions
                        WHERE reference_number IS NOT NULL
                    ),
                    0
                ) > 0
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE property_listing_submissions AS pls
            SET
                reference_number = backup.previous_reference_number,
                payload = CASE
                    WHEN pls.payload ? 'property_details'
                     AND jsonb_typeof(pls.payload -> 'property_details') = 'object'
                     AND backup.previous_payload_reference_number IS NOT NULL
                    THEN jsonb_set(
                        pls.payload,
                        '{{property_details,reference_number}}',
                        to_jsonb(backup.previous_payload_reference_number),
                        true
                    )
                    WHEN pls.payload ? 'property_details'
                     AND jsonb_typeof(pls.payload -> 'property_details') = 'object'
                     AND backup.previous_payload_reference_number IS NULL
                    THEN pls.payload #- '{{property_details,reference_number}}'
                    ELSE pls.payload
                END
            FROM {BACKUP_TABLE} AS backup
            WHERE pls.id = backup.submission_id
            """
        )
    )
    op.execute(sa.text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
