"""Add currency and measurement_unit to agency_master.

Revision ID: 0051_agency_currency_unit
Revises: 0050_add_agency_logo_url
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051_agency_currency_unit"
down_revision: Union[str, Sequence[str], None] = "0050_add_agency_logo_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agency_master",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="JOD"),
    )
    op.add_column(
        "agency_master",
        sa.Column("measurement_unit", sa.String(length=20), nullable=False, server_default="sqm"),
    )


def downgrade() -> None:
    op.drop_column("agency_master", "measurement_unit")
    op.drop_column("agency_master", "currency")
