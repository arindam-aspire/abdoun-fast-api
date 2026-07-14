"""Add agent onboarding profile and invite fields.

Revision ID: 0061_agent_onboarding_fields
Revises: 0060_property_workflow_statuses
Create Date: 2026-07-13

NOTE: This revision was already applied to the demo DB. Kept for Alembic lineage.
Service areas were initially JSONB; 0062 replaces that with a junction table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0061_agent_onboarding_fields"
down_revision = "0060_property_workflow_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_profiles",
        sa.Column("whatsapp_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("position", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column("identity_document_s3_link", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_profiles",
        sa.Column(
            "service_areas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_invites",
        sa.Column("phone_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "agent_invites",
        sa.Column(
            "purpose",
            sa.String(length=20),
            nullable=False,
            server_default="onboarding",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_invites
            SET purpose = 'legacy_accept'
            WHERE purpose = 'onboarding'
              AND created_at < NOW()
              AND is_used = false
              AND revoked_at IS NULL
            """
        )
    )
    op.alter_column("agent_invites", "email", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.alter_column("agent_invites", "email", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("agent_invites", "purpose")
    op.drop_column("agent_invites", "phone_number")
    op.drop_column("agent_profiles", "service_areas")
    op.drop_column("agent_profiles", "identity_document_s3_link")
    op.drop_column("agent_profiles", "position")
    op.drop_column("agent_profiles", "whatsapp_number")
