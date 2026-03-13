"""
Make users.phone_number nullable

Invited agents are created without a phone number; it is set when they
submit the onboarding form. Keeping the column unique so real numbers
remain unique; multiple NULLs are allowed.

Revision ID: 0021_phone_nullable
Revises: 0020_revoked_fields
Create Date: 2026-03-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_phone_nullable"
down_revision: Union[str, None] = "0020_revoked_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "phone_number",
        existing_type=sa.String(20),
        nullable=True,
    )


def downgrade() -> None:
    # Optional: in downgrade you could fail if any NULLs exist, or set a placeholder.
    op.alter_column(
        "users",
        "phone_number",
        existing_type=sa.String(20),
        nullable=False,
    )
