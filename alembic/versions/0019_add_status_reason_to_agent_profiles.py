"""
Add status_reason to agent_profiles

Revision ID: 0019_add_status_reason_to_agent_profiles
Revises: 0018_update_agent_onboarding_fields
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# Keep revision IDs short enough for alembic_version.version_num (VARCHAR(32)).
revision: str = "0019_status_reason"
down_revision: Union[str, None] = "0018_agent_onboarding_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add status_reason column to agent_profiles."""
    op.add_column(
        "agent_profiles",
        sa.Column("status_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop status_reason column from agent_profiles."""
    op.drop_column("agent_profiles", "status_reason")


