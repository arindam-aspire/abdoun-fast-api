"""merge 0034 profile picture and drop created_by_user_id branches

Revision ID: 0035_merge_0034_heads
Revises: 0034_users_profile_pic, 0034_drop_created_by_user_id_dup
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0035_merge_0034_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0034_users_profile_pic",
    "0034_drop_created_by_user_id_dup",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
