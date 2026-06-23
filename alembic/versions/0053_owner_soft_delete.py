"""baseline live demo schema

Revision ID: 0053_owner_soft_delete
Revises: 0003_add_location_name
Create Date: 2026-06-23
"""

revision = "0053_owner_soft_delete"
down_revision = "0003_add_location_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """The authorized test DB already contains this schema revision."""


def downgrade() -> None:
    """No-op baseline marker for the already-applied live schema."""
