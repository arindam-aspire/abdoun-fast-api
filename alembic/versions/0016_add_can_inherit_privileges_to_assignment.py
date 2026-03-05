"""Add can_inherit_privileges to admin_agent_assignments

Revision ID: 0016_add_can_inherit_privileges_to_assignment
Revises: 0015_add_missing_fields_to_user_models
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_can_inherit_privileges"
down_revision: Union[str, None] = "0015_add_user_model_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_agent_assignments",
        sa.Column("can_inherit_privileges", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("admin_agent_assignments", "can_inherit_privileges")
