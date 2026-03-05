"""Remove commission_rate and total_deals from agent_profiles

Revision ID: 0017_remove_commission_and_deals_from_agent_profiles
Revises: 0016_add_can_inherit_privileges_to_assignment
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_remove_agent_commission"
down_revision: Union[str, None] = "0016_can_inherit_privileges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("agent_profiles", "total_deals")
    op.drop_column("agent_profiles", "commission_rate")


def downgrade() -> None:
    op.add_column("agent_profiles", sa.Column("commission_rate", sa.Float(), nullable=True))
    op.add_column(
        "agent_profiles",
        sa.Column("total_deals", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
