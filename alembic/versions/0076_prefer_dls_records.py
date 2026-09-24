"""Prefer dls_records and drop duplicate dls_locations.

Revision ID: 0076_prefer_dls_records
Revises: 0075_land_type_options
Create Date: 2026-09-24

dls_locations and dls_records hold the same DLS hierarchy. The live app
contract uses gov_* columns on dls_records; dls_locations was left with
legacy government_* columns after an earlier rename. Keep dls_records and
remove dls_locations.
"""

from __future__ import annotations

import csv
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0076_prefer_dls_records"
down_revision = "0075_land_type_options"
branch_labels = None
depends_on = None

CSV_PATH = Path(__file__).resolve().parents[2] / "app" / "config" / "dls_locations.csv"
COLUMNS = (
    "gov_code",
    "gov_name",
    "dept_code",
    "dept_name",
    "vill_code",
    "vill_name",
    "hod_code",
    "hod_name",
    "sect_code",
    "sect_name",
)


def _table_names(conn) -> set[str]:
    inspector = sa.inspect(conn)
    return set(inspector.get_table_names())


def _column_names(conn, table: str) -> set[str]:
    inspector = sa.inspect(conn)
    return {column["name"] for column in inspector.get_columns(table)}


def _seed_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "gov_code": row["GOV_CODE"],
                "gov_name": row["GOV_NAME"],
                "dept_code": row["DEPT_CODE"],
                "dept_name": row["DEPT_NAME"],
                "vill_code": row["VILL_CODE"],
                "vill_name": row["VILL_NAME"],
                "hod_code": row["HOD_CODE"],
                "hod_name": row["HOD_NAME"],
                "sect_code": row["SECT_CODE"],
                "sect_name": row["SECT_NAME"],
            }
            for row in reader
        ]


def _create_dls_records_table() -> None:
    op.create_table(
        "dls_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("gov_code", sa.String(length=50), nullable=False),
        sa.Column("gov_name", sa.String(length=255), nullable=False),
        sa.Column("dept_code", sa.String(length=50), nullable=False),
        sa.Column("dept_name", sa.String(length=255), nullable=False),
        sa.Column("vill_code", sa.String(length=50), nullable=False),
        sa.Column("vill_name", sa.String(length=255), nullable=False),
        sa.Column("hod_code", sa.String(length=50), nullable=False),
        sa.Column("hod_name", sa.String(length=255), nullable=False),
        sa.Column("sect_code", sa.String(length=50), nullable=False),
        sa.Column("sect_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint(
            "gov_code",
            "dept_code",
            "vill_code",
            "hod_code",
            "sect_code",
            name="uq_dls_records_hierarchy",
        ),
    )
    op.create_index("idx_dls_gov", "dls_records", ["gov_code"])
    op.create_index("idx_dls_dept", "dls_records", ["gov_code", "dept_code"])
    op.create_index("idx_dls_vill", "dls_records", ["gov_code", "dept_code", "vill_code"])
    op.create_index(
        "idx_dls_hod",
        "dls_records",
        ["gov_code", "dept_code", "vill_code", "hod_code"],
    )
    op.create_index(
        "idx_dls_hierarchy",
        "dls_records",
        ["gov_code", "dept_code", "vill_code", "hod_code", "sect_code"],
    )


def _seed_dls_records() -> None:
    table = sa.table("dls_records", *[sa.column(name, sa.String()) for name in COLUMNS])
    rows = _seed_rows()
    batch_size = 1000
    for start in range(0, len(rows), batch_size):
        op.bulk_insert(table, rows[start : start + batch_size])


def _copy_locations_into_records(conn, *, source_gov_code: str, source_gov_name: str) -> None:
    conn.execute(
        sa.text(
            f"""
            INSERT INTO dls_records (
                gov_code, gov_name, dept_code, dept_name,
                vill_code, vill_name, hod_code, hod_name,
                sect_code, sect_name
            )
            SELECT
                {source_gov_code}, {source_gov_name}, dept_code, dept_name,
                vill_code, vill_name, hod_code, hod_name,
                sect_code, sect_name
            FROM dls_locations
            ON CONFLICT (gov_code, dept_code, vill_code, hod_code, sect_code) DO NOTHING
            """
        )
    )


def _drop_dls_locations_if_present(conn) -> None:
    if "dls_locations" not in _table_names(conn):
        return
    op.execute(sa.text("DROP TABLE IF EXISTS dls_locations CASCADE"))


def _ensure_records_unique_constraint(conn) -> None:
    constraints = {
        constraint["name"]
        for constraint in sa.inspect(conn).get_unique_constraints("dls_records")
    }
    if "uq_dls_records_hierarchy" in constraints:
        return
    # Skip if duplicates would block the constraint.
    dupes = conn.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM (
                SELECT gov_code, dept_code, vill_code, hod_code, sect_code
                FROM dls_records
                GROUP BY 1, 2, 3, 4, 5
                HAVING COUNT(*) > 1
            ) AS d
            """
        )
    ).scalar()
    if dupes:
        return
    op.create_unique_constraint(
        "uq_dls_records_hierarchy",
        "dls_records",
        ["gov_code", "dept_code", "vill_code", "hod_code", "sect_code"],
    )


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)
    has_locations = "dls_locations" in tables
    has_records = "dls_records" in tables

    if not has_records:
        if has_locations:
            location_cols = _column_names(conn, "dls_locations")
            if "gov_code" in location_cols and "government_code" not in location_cols:
                # Fresh 0072 shape: rename the table and attach timestamps/indexes.
                op.rename_table("dls_locations", "dls_records")
                for old_name, new_name, cols in (
                    ("ix_dls_locations_gov", "idx_dls_gov", ["gov_code"]),
                    ("ix_dls_locations_gov_dept", "idx_dls_dept", ["gov_code", "dept_code"]),
                    (
                        "ix_dls_locations_gov_dept_vill",
                        "idx_dls_vill",
                        ["gov_code", "dept_code", "vill_code"],
                    ),
                    (
                        "ix_dls_locations_gov_dept_vill_hod",
                        "idx_dls_hod",
                        ["gov_code", "dept_code", "vill_code", "hod_code"],
                    ),
                ):
                    op.execute(sa.text(f'DROP INDEX IF EXISTS "{old_name}"'))
                    op.create_index(new_name, "dls_records", cols)
                op.execute(sa.text('DROP INDEX IF EXISTS "uq_dls_locations_hierarchy"'))
                op.execute(
                    sa.text(
                        """
                        ALTER TABLE dls_records
                        DROP CONSTRAINT IF EXISTS uq_dls_locations_hierarchy
                        """
                    )
                )
                op.add_column(
                    "dls_records",
                    sa.Column(
                        "created_at",
                        sa.DateTime(),
                        server_default=sa.text("now()"),
                        nullable=True,
                    ),
                )
                op.add_column(
                    "dls_records",
                    sa.Column(
                        "updated_at",
                        sa.DateTime(),
                        server_default=sa.text("now()"),
                        nullable=True,
                    ),
                )
                op.create_index(
                    "idx_dls_hierarchy",
                    "dls_records",
                    ["gov_code", "dept_code", "vill_code", "hod_code", "sect_code"],
                )
                _ensure_records_unique_constraint(conn)
                return

            # government_* shape without dls_records: create + copy, then drop.
            _create_dls_records_table()
            _copy_locations_into_records(
                conn,
                source_gov_code="government_code",
                source_gov_name="government_name",
            )
            _drop_dls_locations_if_present(conn)
            return

        # Neither table: create and seed from CSV.
        _create_dls_records_table()
        _seed_dls_records()
        return

    # dls_records already present (current live DB): drop the duplicate.
    if has_locations:
        location_cols = _column_names(conn, "dls_locations")
        records_count = conn.execute(sa.text("SELECT COUNT(*) FROM dls_records")).scalar() or 0
        if records_count == 0:
            if "gov_code" in location_cols:
                _copy_locations_into_records(
                    conn,
                    source_gov_code="gov_code",
                    source_gov_name="gov_name",
                )
            elif "government_code" in location_cols:
                _copy_locations_into_records(
                    conn,
                    source_gov_code="government_code",
                    source_gov_name="government_name",
                )
        _drop_dls_locations_if_present(conn)

    _ensure_records_unique_constraint(conn)


def downgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)
    if "dls_locations" in tables or "dls_records" not in tables:
        return

    op.create_table(
        "dls_locations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("gov_code", sa.String(length=50), nullable=False),
        sa.Column("gov_name", sa.String(length=255), nullable=False),
        sa.Column("dept_code", sa.String(length=50), nullable=False),
        sa.Column("dept_name", sa.String(length=255), nullable=False),
        sa.Column("vill_code", sa.String(length=50), nullable=False),
        sa.Column("vill_name", sa.String(length=255), nullable=False),
        sa.Column("hod_code", sa.String(length=50), nullable=False),
        sa.Column("hod_name", sa.String(length=255), nullable=False),
        sa.Column("sect_code", sa.String(length=50), nullable=False),
        sa.Column("sect_name", sa.String(length=255), nullable=False),
        sa.UniqueConstraint(
            "gov_code",
            "dept_code",
            "vill_code",
            "hod_code",
            "sect_code",
            name="uq_dls_locations_hierarchy",
        ),
    )
    op.create_index("ix_dls_locations_gov", "dls_locations", ["gov_code"])
    op.create_index("ix_dls_locations_gov_dept", "dls_locations", ["gov_code", "dept_code"])
    op.create_index(
        "ix_dls_locations_gov_dept_vill",
        "dls_locations",
        ["gov_code", "dept_code", "vill_code"],
    )
    op.create_index(
        "ix_dls_locations_gov_dept_vill_hod",
        "dls_locations",
        ["gov_code", "dept_code", "vill_code", "hod_code"],
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO dls_locations (
                gov_code, gov_name, dept_code, dept_name,
                vill_code, vill_name, hod_code, hod_name,
                sect_code, sect_name
            )
            SELECT
                gov_code, gov_name, dept_code, dept_name,
                vill_code, vill_name, hod_code, hod_name,
                sect_code, sect_name
            FROM dls_records
            """
        )
    )
