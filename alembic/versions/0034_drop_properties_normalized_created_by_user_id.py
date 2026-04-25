"""drop duplicate created_by_user_id; use created_by only on properties_normalized

Revision ID: 0034_drop_created_by_user_id_dup
Revises: 0033_pr_ch_cog_sess
Create Date: 2026-04-25

Older installs ran 0028_property_user_tracking before it stopped adding
created_by_user_id (duplicate of created_by from 0028_prop_listing_subs).
This migration merges any stray values into created_by and removes the column.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "0034_drop_created_by_user_id_dup"
down_revision: Union[str, None] = "0033_pr_ch_cog_sess"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    col_names = {c["name"] for c in insp.get_columns("properties_normalized")}
    if "created_by_user_id" not in col_names:
        return

    op.execute(
        sa.text(
            """
            UPDATE properties_normalized
            SET created_by = created_by_user_id
            WHERE created_by IS NULL AND created_by_user_id IS NOT NULL
            """
        )
    )

    op.drop_index(
        "ix_properties_created_by_user_id",
        table_name="properties_normalized",
    )
    op.drop_constraint(
        "fk_properties_created_by_user",
        "properties_normalized",
        type_="foreignkey",
    )
    op.drop_column("properties_normalized", "created_by_user_id")


def downgrade() -> None:
    op.add_column(
        "properties_normalized",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE properties_normalized
            SET created_by_user_id = created_by
            WHERE created_by IS NOT NULL
            """
        )
    )
    op.create_foreign_key(
        "fk_properties_created_by_user",
        "properties_normalized",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_properties_created_by_user_id",
        "properties_normalized",
        ["created_by_user_id"],
        unique=False,
    )
