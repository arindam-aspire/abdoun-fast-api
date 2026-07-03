"""add configurable property workflow statuses

Revision ID: 0060_property_workflow_statuses
Revises: 0059_add_deactivated_status
Create Date: 2026-07-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0060_property_workflow_statuses"
down_revision = "0059_add_deactivated_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statuses = [
        ("Draft", "draft", 1),
        ("Submitted", "submitted", 2),
        ("Agent Assigned", "agent-assigned", 3),
        ("Pending Approval", "pending-approval", 4),
        ("Active", "active", 5),
        ("Rejected", "rejected", 6),
        ("Deactivated", "deactivated", 7),
        ("Deal Closure Requested", "deal-closure-requested", 8),
        ("Deal Closed", "deal-closed", 9),
    ]
    for name, slug, display_order in statuses:
        op.execute(
            sa.text(
                """
                INSERT INTO property_status (name, slug, is_active, display_order, created_at, updated_at)
                VALUES (:name, :slug, true, :display_order, now(), now())
                ON CONFLICT (slug) DO UPDATE
                SET name = EXCLUDED.name,
                    is_active = true,
                    display_order = EXCLUDED.display_order,
                    updated_at = now()
                """
            ).bindparams(name=name, slug=slug, display_order=display_order)
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE property_status
            SET is_active = false,
                display_order = NULL,
                updated_at = now()
            WHERE slug IN ('submitted', 'agent-assigned')
            """
        )
    )
