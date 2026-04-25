"""add profile_picture_url to users

Revision ID: 0034_users_profile_pic
Revises: 0033_pr_ch_cog_sess
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0034_users_profile_pic"
down_revision: Union[str, None] = "0033_pr_ch_cog_sess"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_picture_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_picture_url")
