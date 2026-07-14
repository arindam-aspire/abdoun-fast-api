"""Replace agent service_areas JSONB with junction table.

Revision ID: 0062_agent_service_areas
Revises: 0061_agent_onboarding_fields
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0062_agent_service_areas"
down_revision = "0061_agent_onboarding_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_service_areas",
        sa.Column("agent_user_id", sa.UUID(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["agent_user_id"], ["agent_profiles.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["area_id"], ["areas.id"]),
        sa.PrimaryKeyConstraint("agent_user_id", "area_id"),
    )
    op.create_index(
        "ix_agent_service_areas_area_id",
        "agent_service_areas",
        ["area_id"],
    )
    op.drop_column("agent_profiles", "service_areas")


def downgrade() -> None:
    op.add_column(
        "agent_profiles",
        sa.Column("service_areas", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_index("ix_agent_service_areas_area_id", table_name="agent_service_areas")
    op.drop_table("agent_service_areas")
