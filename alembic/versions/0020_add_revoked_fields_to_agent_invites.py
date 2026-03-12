"""
Add revoked_at and revoked_by to agent_invites

Revision ID: 0020_add_revoked_fields_to_agent_invites
Revises: 0019_add_status_reason_to_agent_profiles
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# Keep revision IDs short enough for alembic_version.version_num (VARCHAR(32)).
revision: str = "0020_revoked_fields"
down_revision: Union[str, None] = "0019_status_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add revoked_at and revoked_by columns to agent_invites."""
    op.add_column(
        "agent_invites",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_invites",
        sa.Column("revoked_by", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_invites_revoked_by",
        "agent_invites",
        "users",
        ["revoked_by"],
        ["id"],
        ondelete="SET NULL"
    )


def downgrade() -> None:
    """Drop revoked_at and revoked_by columns from agent_invites."""
    op.drop_constraint("fk_agent_invites_revoked_by", "agent_invites", type_="foreignkey")
    op.drop_column("agent_invites", "revoked_by")
    op.drop_column("agent_invites", "revoked_at")

