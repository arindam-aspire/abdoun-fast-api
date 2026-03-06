"""Update agent onboarding fields

Revision ID: 0018_update_agent_onboarding_fields
Revises: 0017_remove_agent_commission
Create Date: 2026-03-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0018_agent_onboarding_fields"
down_revision: Union[str, None] = "0017_remove_agent_commission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new fields to agent_profiles
    op.add_column(
        "agent_profiles",
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("form_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("password_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("decline_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    
    # Update status column to support new statuses (change default and add index)
    op.alter_column(
        "agent_profiles",
        "status",
        existing_type=sa.String(20),
        server_default="INVITED",
        nullable=False,
    )
    
    # Create index on status for faster filtering
    op.create_index(
        "ix_agent_profiles_status",
        "agent_profiles",
        ["status"],
        unique=False,
    )
    
    # Create index on deleted_at for soft delete filtering
    op.create_index(
        "ix_agent_profiles_deleted_at",
        "agent_profiles",
        ["deleted_at"],
        unique=False,
    )
    
    # Add foreign key constraints for reviewed_by and deleted_by
    op.create_foreign_key(
        "fk_agent_profiles_reviewed_by",
        "agent_profiles",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_profiles_deleted_by",
        "agent_profiles",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    
    # Add invited_at to agent_invites (if not exists)
    # Check if column exists first - if it does, skip
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("agent_invites")]
    
    if "invited_at" not in columns:
        op.add_column(
            "agent_invites",
            sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        )
    
    # Migrate existing data: set status to PENDING_REVIEW for existing pending agents
    op.execute(
        """
        UPDATE agent_profiles
        SET status = 'PENDING_REVIEW'
        WHERE status = 'pending'
        """
    )
    
    # Migrate existing data: set status to DECLINED for existing rejected agents
    op.execute(
        """
        UPDATE agent_profiles
        SET status = 'DECLINED'
        WHERE status = 'rejected'
        """
    )
    
    # Migrate existing data: set status to ACTIVE for existing approved agents
    op.execute(
        """
        UPDATE agent_profiles
        SET status = 'ACTIVE'
        WHERE status = 'approved'
        """
    )


def downgrade() -> None:
    # Remove foreign key constraints
    op.drop_constraint("fk_agent_profiles_deleted_by", "agent_profiles", type_="foreignkey")
    op.drop_constraint("fk_agent_profiles_reviewed_by", "agent_profiles", type_="foreignkey")
    
    # Drop indexes
    op.drop_index("ix_agent_profiles_deleted_at", table_name="agent_profiles")
    op.drop_index("ix_agent_profiles_status", table_name="agent_profiles")
    
    # Revert status values
    op.execute(
        """
        UPDATE agent_profiles
        SET status = 'pending'
        WHERE status = 'PENDING_REVIEW'
        """
    )
    op.execute(
        """
        UPDATE agent_profiles
        SET status = 'rejected'
        WHERE status = 'DECLINED'
        """
    )
    op.execute(
        """
        UPDATE agent_profiles
        SET status = 'approved'
        WHERE status = 'ACTIVE'
        """
    )
    
    # Revert status column default
    op.alter_column(
        "agent_profiles",
        "status",
        existing_type=sa.String(20),
        server_default="pending",
        nullable=False,
    )
    
    # Remove columns from agent_profiles
    op.drop_column("agent_profiles", "deleted_by")
    op.drop_column("agent_profiles", "deleted_at")
    op.drop_column("agent_profiles", "decline_reason")
    op.drop_column("agent_profiles", "password_set_at")
    op.drop_column("agent_profiles", "form_submitted_at")
    op.drop_column("agent_profiles", "reviewed_at")
    op.drop_column("agent_profiles", "reviewed_by")
    
    # Remove invited_at from agent_invites if it exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("agent_invites")]
    
    if "invited_at" in columns:
        op.drop_column("agent_invites", "invited_at")

