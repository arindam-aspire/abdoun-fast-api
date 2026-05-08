"""Add lead_number (display reference) and atomic yearly counter.

Revision ID: 0040_lead_display_identifiers
Revises: 0039_lead_lifecycle
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "0040_lead_display_identifiers"
down_revision: Union[str, Sequence[str], None] = "0039_lead_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_number_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("year"),
    )

    op.add_column("leads", sa.Column("lead_number", sa.String(length=32), nullable=True))

    bind = op.get_bind()

    rows = bind.execute(
        text("SELECT id, created_at FROM leads ORDER BY created_at ASC NULLS LAST, id ASC")
    ).fetchall()

    by_year: dict[int, list[str]] = defaultdict(list)
    for rid, created_at in rows:
        if created_at is not None:
            y = int(created_at.year)
        else:
            res = bind.execute(text("SELECT EXTRACT(YEAR FROM CURRENT_TIMESTAMP)::int"))
            y = int(res.scalar_one())
        by_year[y].append(str(rid))

    for year in sorted(by_year.keys()):
        for idx, lead_id in enumerate(by_year[year], start=1):
            lead_number = f"LD-{year}-{idx:06d}"
            bind.execute(
                text("UPDATE leads SET lead_number = :ln WHERE id = :id"),
                {"ln": lead_number, "id": lead_id},
            )
        bind.execute(
            text("INSERT INTO lead_number_counters (year, last_value) VALUES (:y, :v)"),
            {"y": year, "v": len(by_year[year])},
        )

    op.alter_column(
        "leads",
        "lead_number",
        existing_type=sa.String(length=32),
        nullable=False,
    )

    op.create_index("ix_leads_lead_number", "leads", ["lead_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_leads_lead_number", table_name="leads")
    op.drop_column("leads", "lead_number")
    op.drop_table("lead_number_counters")
