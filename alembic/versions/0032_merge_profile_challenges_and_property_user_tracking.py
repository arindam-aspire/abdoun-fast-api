"""merge divergent branches (property user tracking vs submissions/profile OTP)

Revision ID: 0032_merge_heads
Revises: 0031_profile_challenges, 0028_property_user_tracking
Create Date: 2026-04-24

Two parallel chains both forked from 0027_recently_viewed_properties:
- 0028_prop_listing_subs → … → 0031_profile_challenges
- 0028_property_user_tracking (no further revisions)

This revision merges them so `alembic upgrade head` is unambiguous.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0032_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0031_profile_challenges",
    "0028_property_user_tracking",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
