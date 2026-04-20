"""add virtual_tour_url column to properties_normalized

Revision ID: 0025_add_virtual_tour_url
Revises: 0024_user_property_favorites
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0025_add_virtual_tour_url"
down_revision: Union[str, None] = "0024_user_property_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "properties_normalized",
        sa.Column("virtual_tour_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties_normalized", "virtual_tour_url")
