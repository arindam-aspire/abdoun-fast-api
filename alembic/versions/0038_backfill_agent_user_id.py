"""Backfill agent_user_id for agent-created properties.

Revision ID: 0038_backfill_agent
Revises: 0037_soft_delete_props
Create Date: 2026-04-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0038_backfill_agent"
down_revision: Union[str, Sequence[str], None] = "0037_soft_delete_props"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For properties created by an agent, treat the creator as the default assigned/listing agent.
    # This enables admin UI to correctly hide "Assign Agent" for agent-created listings.
    op.execute(
        sa.text(
            """
            UPDATE properties_normalized p
            SET agent_user_id = p.created_by
            WHERE p.agent_user_id IS NULL
              AND p.created_by IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = p.created_by
                  AND r.name = 'agent'
              )
            """
        )
    )


def downgrade() -> None:
    # Best-effort reversal: only clear agent_user_id when it exactly equals created_by.
    op.execute(
        sa.text(
            """
            UPDATE properties_normalized p
            SET agent_user_id = NULL
            WHERE p.agent_user_id = p.created_by
            """
        )
    )

