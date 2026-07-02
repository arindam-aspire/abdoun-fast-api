"""add deactivated property status

Revision ID: 0059_add_deactivated_status
Revises: 0058_dco_status_cleanup
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0059_add_deactivated_status"
down_revision = "0058_dco_status_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO property_status (name, slug, is_active, display_order, created_at, updated_at)
            VALUES ('Deactivated', 'deactivated', true, 7, now(), now())
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                is_active = true,
                display_order = EXCLUDED.display_order,
                updated_at = now()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE property_status
            SET is_active = false,
                display_order = NULL,
                updated_at = now()
            WHERE slug = 'deactivated'
            """
        )
    )
