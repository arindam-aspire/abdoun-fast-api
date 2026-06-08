"""Add agency logo_url column.

Revision ID: 0050_add_agency_logo_url
Revises: 0049_extend_features_taxonomy
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050_add_agency_logo_url"
down_revision: Union[str, Sequence[str], None] = "0049_extend_features_taxonomy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agency_master", sa.Column("logo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agency_master", "logo_url")
