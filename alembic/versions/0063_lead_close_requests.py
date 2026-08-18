"""Add pending lead close-request workflow.

Revision ID: 0063_lead_close_requests
Revises: 0062_agent_service_areas
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0063_lead_close_requests"
down_revision = "0062_agent_service_areas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_close_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("canceled_by", sa.UUID(), nullable=True),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["canceled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_close_requests_lead_status",
        "lead_close_requests",
        ["lead_id", "status"],
    )
    op.create_index(
        "uq_lead_close_requests_pending",
        "lead_close_requests",
        ["lead_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_lead_close_requests_pending", table_name="lead_close_requests")
    op.drop_index("ix_lead_close_requests_lead_status", table_name="lead_close_requests")
    op.drop_table("lead_close_requests")
