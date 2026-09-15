"""Create and seed the official DLS location master table.

Revision ID: 0072_dls_locations
Revises: 0071_add_property_uat
Create Date: 2026-09-15
"""

from __future__ import annotations

import csv
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0072_dls_locations"
down_revision = "0071_add_property_uat"
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


def upgrade() -> None:
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

    table = sa.table("dls_locations", *[sa.column(name, sa.String()) for name in COLUMNS])
    rows = _seed_rows()
    batch_size = 1000
    for start in range(0, len(rows), batch_size):
        op.bulk_insert(table, rows[start : start + batch_size])


def downgrade() -> None:
    op.drop_index("ix_dls_locations_gov_dept_vill_hod", table_name="dls_locations")
    op.drop_index("ix_dls_locations_gov_dept_vill", table_name="dls_locations")
    op.drop_index("ix_dls_locations_gov_dept", table_name="dls_locations")
    op.drop_index("ix_dls_locations_gov", table_name="dls_locations")
    op.drop_table("dls_locations")
