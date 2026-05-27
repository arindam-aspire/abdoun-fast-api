"""Add agency registration tables and user linkage.

Revision ID: 0047_agency_registration
Revises: 0046_password_login_lockout
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision: str = "0047_agency_registration"
down_revision: Union[str, Sequence[str], None] = "0046_password_login_lockout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agency_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agency_name", sa.String(length=255), nullable=False),
        sa.Column("agency_trade_name", sa.String(length=255), nullable=False),
        sa.Column("legal_document_s3_link", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_agency_master_email"),
        sa.UniqueConstraint("phone", name="uq_agency_master_phone"),
    )
    op.create_index("ix_agency_master_email", "agency_master", ["email"], unique=False)
    op.create_index("ix_agency_master_phone", "agency_master", ["phone"], unique=False)
    op.add_column("users", sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.create_index("ix_users_agency_id", "users", ["agency_id"], unique=False)
    op.create_foreign_key(
        "fk_users_agency_id_agency_master",
        "users",
        "agency_master",
        ["agency_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for name, description in (
        ("super_admin", "Platform super administrator"),
        ("admin", "Administrator"),
    ):
        op.execute(
            sa.text(
                """
                INSERT INTO roles (id, name, description)
                VALUES (:id, :name, :description)
                ON CONFLICT (name) DO NOTHING
                """
            ).bindparams(id=str(uuid.uuid4()), name=name, description=description)
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name = 'super_admin'")
    op.drop_constraint("fk_users_agency_id_agency_master", "users", type_="foreignkey")
    op.drop_index("ix_users_agency_id", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "agency_id")
    op.drop_index("ix_agency_master_phone", table_name="agency_master")
    op.drop_index("ix_agency_master_email", table_name="agency_master")
    op.drop_table("agency_master")
