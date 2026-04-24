"""profile change challenges: store Cognito CUSTOM_AUTH session for email OTP

Revision ID: 0033_pr_ch_cog_sess
Revises: 0032_merge_heads
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0033_pr_ch_cog_sess"
down_revision: Union[str, None] = "0032_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profile_change_challenges",
        sa.Column("cognito_custom_auth_session", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profile_change_challenges", "cognito_custom_auth_session")
