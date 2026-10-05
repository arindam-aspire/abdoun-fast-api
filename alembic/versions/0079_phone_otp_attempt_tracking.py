"""Track phone OTP attempts and consumption.

Revision ID: 0079_phone_otp_attempts
Revises: 0078_agency_invitation_document
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0079_phone_otp_attempts"
down_revision = "0078_agency_invitation_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profile_change_challenges",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_profile_change_challenges",
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_user_profile_change_challenges_user_purpose_created",
        "user_profile_change_challenges",
        ["user_id", "purpose", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_profile_change_challenges_user_purpose_created",
        table_name="user_profile_change_challenges",
    )
    op.drop_column("user_profile_change_challenges", "consumed_at")
    op.drop_column("user_profile_change_challenges", "attempt_count")
