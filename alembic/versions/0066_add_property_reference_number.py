"""Add unique server-generated property reference_number.

Revision ID: 0066_property_ref_number
Revises: 0065_add_property_show_location
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0066_property_ref_number"
down_revision = "0065_add_property_show_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_listing_submissions",
        sa.Column("reference_number", sa.String(length=128), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE property_listing_submissions AS pls
            SET reference_number = src.ref
            FROM (
                SELECT DISTINCT ON (btrim(payload #>> '{property_details,reference_number}'))
                    id,
                    btrim(payload #>> '{property_details,reference_number}') AS ref
                FROM property_listing_submissions
                WHERE nullif(btrim(payload #>> '{property_details,reference_number}'), '') IS NOT NULL
                ORDER BY
                    btrim(payload #>> '{property_details,reference_number}'),
                    created_at ASC NULLS LAST,
                    id ASC
            ) AS src
            WHERE pls.id = src.id
            """
        )
    )
    op.create_index(
        "uq_property_listing_submissions_reference_number",
        "property_listing_submissions",
        ["reference_number"],
        unique=True,
        postgresql_where=sa.text("reference_number IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_property_listing_submissions_reference_number",
        table_name="property_listing_submissions",
    )
    op.drop_column("property_listing_submissions", "reference_number")
