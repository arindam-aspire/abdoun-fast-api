"""Add owner role seed.

Revision ID: 0048_add_owner_role
Revises: 0047_agency_registration
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.exc import NoSuchTableError


revision: str = "0048_add_owner_role"
down_revision: Union[str, Sequence[str], None] = "0047_agency_registration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNER_ROLE_ID = "550e8400-e29b-41d4-a716-446655440000"
PUBLIC_SCHEMA = "public"
PROPERTY_TABLE = "properties_normalized"
AGENCY_TABLE = "agency_master"
AGENCY_COLUMN = "agency_id"
AGENCY_INDEX = "ix_properties_normalized_agency_id"
AGENCY_FK = "fk_properties_normalized_agency_id_agency_master"


def _table_exists(bind: Connection, table_name: str, schema: str = PUBLIC_SCHEMA) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names(schema=schema)


def _column_exists(
    bind: Connection,
    *,
    table_name: str,
    column_name: str,
    schema: str = PUBLIC_SCHEMA,
) -> bool:
    try:
        columns = sa.inspect(bind).get_columns(table_name, schema=schema)
    except NoSuchTableError:
        return False
    return any(c.get("name") == column_name for c in columns)


def _index_exists(
    bind: Connection,
    *,
    table_name: str,
    index_name: str,
    schema: str = PUBLIC_SCHEMA,
) -> bool:
    try:
        indexes = sa.inspect(bind).get_indexes(table_name, schema=schema)
    except NoSuchTableError:
        return False
    return any(i.get("name") == index_name for i in indexes)


def _fk_exists(
    bind: Connection,
    *,
    table_name: str,
    fk_name: str,
    schema: str = PUBLIC_SCHEMA,
) -> bool:
    try:
        fks = sa.inspect(bind).get_foreign_keys(table_name, schema=schema)
    except NoSuchTableError:
        return False
    return any(fk.get("name") == fk_name for fk in fks)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        sa.text(
            """
            INSERT INTO public.roles (id, name, description, created_at, updated_at)
            VALUES (:id, :name, :description, NOW(), NOW())
            ON CONFLICT (name) DO NOTHING
            """
        ).bindparams(
            id=OWNER_ROLE_ID,
            name="owner",
            description="Owner role with full permissions",
        )
    )

    # Safety check: this migration depends on normalized property schema being present.
    if not _table_exists(bind, PROPERTY_TABLE, schema=PUBLIC_SCHEMA):
        raise RuntimeError(
            "Missing table public.properties_normalized. "
            "Apply the base property creation migrations before running 0048."
        )
    if not _table_exists(bind, AGENCY_TABLE, schema=PUBLIC_SCHEMA):
        raise RuntimeError(
            "Missing table public.agency_master. "
            "Apply dependency revision 0047_agency_registration before running 0048."
        )

    if not _column_exists(
        bind,
        table_name=PROPERTY_TABLE,
        column_name=AGENCY_COLUMN,
        schema=PUBLIC_SCHEMA,
    ):
        op.add_column(
            PROPERTY_TABLE,
            sa.Column(AGENCY_COLUMN, postgresql.UUID(as_uuid=True), nullable=True),
            schema=PUBLIC_SCHEMA,
        )

    if not _index_exists(
        bind,
        table_name=PROPERTY_TABLE,
        index_name=AGENCY_INDEX,
        schema=PUBLIC_SCHEMA,
    ):
        op.create_index(
            AGENCY_INDEX,
            PROPERTY_TABLE,
            [AGENCY_COLUMN],
            unique=False,
            schema=PUBLIC_SCHEMA,
        )

    if not _fk_exists(
        bind,
        table_name=PROPERTY_TABLE,
        fk_name=AGENCY_FK,
        schema=PUBLIC_SCHEMA,
    ):
        op.create_foreign_key(
            AGENCY_FK,
            PROPERTY_TABLE,
            AGENCY_TABLE,
            [AGENCY_COLUMN],
            ["id"],
            source_schema=PUBLIC_SCHEMA,
            referent_schema=PUBLIC_SCHEMA,
            ondelete="SET NULL",
        )

    op.execute(
        sa.text(
            """
            UPDATE properties_normalized p
            SET agency_id = COALESCE(
                (SELECT u.agency_id FROM users u WHERE u.id = p.agent_user_id),
                (SELECT u2.agency_id FROM users u2 WHERE u2.id = p.created_by)
            )
            WHERE p.agency_id IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, PROPERTY_TABLE, schema=PUBLIC_SCHEMA):
        if _fk_exists(
            bind,
            table_name=PROPERTY_TABLE,
            fk_name=AGENCY_FK,
            schema=PUBLIC_SCHEMA,
        ):
            op.drop_constraint(
                AGENCY_FK,
                PROPERTY_TABLE,
                type_="foreignkey",
                schema=PUBLIC_SCHEMA,
            )
        if _index_exists(
            bind,
            table_name=PROPERTY_TABLE,
            index_name=AGENCY_INDEX,
            schema=PUBLIC_SCHEMA,
        ):
            op.drop_index(
                AGENCY_INDEX,
                table_name=PROPERTY_TABLE,
                schema=PUBLIC_SCHEMA,
            )
        if _column_exists(
            bind,
            table_name=PROPERTY_TABLE,
            column_name=AGENCY_COLUMN,
            schema=PUBLIC_SCHEMA,
        ):
            op.drop_column(
                PROPERTY_TABLE,
                AGENCY_COLUMN,
                schema=PUBLIC_SCHEMA,
            )
    op.execute("DELETE FROM public.roles WHERE name = 'owner'")

