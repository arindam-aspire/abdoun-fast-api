"""Add missing fields to user models (agent_profiles commission_rate, total_deals)

Revision ID: 0015_add_missing_fields_to_user_models
Revises: 0014_add_authentication_and_rbac_models
Create Date: 2026-02-26 19:57:58.518917

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_add_user_model_fields"
down_revision: Union[str, None] = "0014_add_auth_rbac_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_profiles", sa.Column("commission_rate", sa.Float(), nullable=True))
    op.add_column("agent_profiles", sa.Column("total_deals", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("agent_profiles", "total_deals")
    op.drop_column("agent_profiles", "commission_rate")
