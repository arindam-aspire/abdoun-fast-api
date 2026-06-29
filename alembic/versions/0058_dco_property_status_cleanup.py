"""normalize dco property status values

Revision ID: 0058_dco_status_cleanup
Revises: 0057_dco_taxonomy_order
Create Date: 2026-06-29
"""

from alembic import op


revision = "0058_dco_status_cleanup"
down_revision = "0057_dco_taxonomy_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE property_listing_submissions
        SET status = 'pending-approval',
            updated_at = now()
        WHERE status IN ('submitted', 'pending', 'pending_admin_approval')
        """
    )
    op.execute(
        """
        UPDATE property_listing_submissions
        SET status = 'active',
            updated_at = now()
        WHERE status IN ('approved', 'verified', 'available')
        """
    )
    op.execute(
        """
        UPDATE property_status
        SET is_active = false,
            display_order = NULL,
            updated_at = now()
        WHERE slug IN ('approved', 'available', 'verified', 'pending', 'sold', 'rented')
        """
    )
    op.execute(
        """
        UPDATE property_status
        SET is_active = true,
            updated_at = now()
        WHERE slug IN ('draft', 'pending-approval', 'active', 'rejected', 'deal-closure-requested', 'deal-closed')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE property_listing_submissions
        SET status = 'submitted',
            updated_at = now()
        WHERE status = 'pending-approval'
        """
    )
    op.execute(
        """
        UPDATE property_listing_submissions
        SET status = 'approved',
            updated_at = now()
        WHERE status = 'active'
        """
    )
    op.execute(
        """
        UPDATE property_status
        SET is_active = true,
            updated_at = now()
        WHERE slug IN ('approved', 'available')
        """
    )
