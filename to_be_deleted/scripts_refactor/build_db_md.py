"""Regenerate db.md from live PostgreSQL (uses .env DATABASE_URL)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"], future=True)

lines: list[str] = []


def out(s: str = "") -> None:
    lines.append(s)


def main() -> None:
    out("# Database schema (Abdoun FastAPI)")
    out()
    out(
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC. "
        "Source: introspection of PostgreSQL using `DATABASE_URL` from `.env` (secrets not stored in this file)._"
    )
    out()
    out("## Connection")
    out()
    out("- Driver: PostgreSQL (SQLAlchemy / `postgresql+psycopg2` as configured in `.env`).")
    out("- Credentials and host are only in `.env`; not duplicated here.")
    out()

    with engine.connect() as conn:
        out("## PostgreSQL extensions")
        out()
        out("| Extension | Version |")
        out("|-----------|---------|")
        r = conn.execute(text("SELECT extname, extversion FROM pg_extension ORDER BY extname"))
        for row in r:
            out(f"| `{row[0]}` | {row[1]} |")
        out()

        out("## Schemas (non-system)")
        out()
        r = conn.execute(
            text(
                """
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                ORDER BY schema_name
                """
            )
        )
        for row in r:
            out(f"- `{row[0]}`")
        out()

        out("## Alembic revision (database)")
        out()
        r = conn.execute(text("SELECT version_num FROM alembic_version"))
        rows = list(r)
        if rows:
            out(f"- `{rows[0][0]}`")
        else:
            out("- _(no row in `alembic_version`)_")
        out()

        out("## Views")
        out()
        out("| Schema | Name | Type |")
        out("|--------|------|------|")
        r = conn.execute(
            text(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_type = 'VIEW'
                ORDER BY table_schema, table_name
                """
            )
        )
        for row in r:
            out(f"| `{row[0]}` | `{row[1]}` | {row[2]} |")
        out()

        out("## Sequences")
        out()
        out("| Schema | Sequence | Data type |")
        out("|--------|----------|-----------|")
        r = conn.execute(
            text(
                """
                SELECT sequence_schema, sequence_name, data_type
                FROM information_schema.sequences
                WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY sequence_schema, sequence_name
                """
            )
        )
        for row in r:
            out(f"| `{row[0]}` | `{row[1]}` | {row[2]} |")
        out()

        out("## Base tables (summary)")
        out()
        r = conn.execute(
            text(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
                """
            )
        )
        tables: list[tuple[str, str]] = [(row[0], row[1]) for row in r]
        for schema, name in tables:
            out(f"- `{schema}.{name}`")
        out()

        out("## Foreign keys")
        out()
        r = conn.execute(
            text(
                """
                SELECT
                    tc.table_schema,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_schema AS foreign_table_schema,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    tc.constraint_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
                """
            )
        )
        out("| From | Column | To | FK name |")
        out("|------|--------|----|---------|")
        for row in r:
            src = f"`{row[0]}.{row[1]}`"
            dst = f"`{row[3]}.{row[4]}` (`{row[5]}`)"
            out(f"| {src} | `{row[2]}` | {dst} | `{row[6]}` |")
        out()

        out("## Indexes (user schemas)")
        out()
        r = conn.execute(
            text(
                """
                SELECT schemaname, tablename, indexname, indexdef
                FROM pg_indexes
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schemaname, tablename, indexname
                """
            )
        )
        current_table: str | None = None
        for row in r:
            key = f"{row[0]}.{row[1]}"
            if key != current_table:
                current_table = key
                out()
                out(f"### `{key}`")
                out()
            out(f"- `{row[2]}`: `{row[3]}`")
        out()

        out("## Columns by table")
        out()
        for schema, name in tables:
            out(f"### `{schema}.{name}`")
            out()
            out(
                "| # | Column | Data type | UDT | Nullable | Default |"
            )
            out("|---|--------|-----------|-----|----------|---------|")
            r = conn.execute(
                text(
                    """
                    SELECT ordinal_position, column_name, data_type, udt_name,
                           is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = :s AND table_name = :t
                    ORDER BY ordinal_position
                    """
                ),
                {"s": schema, "t": name},
            )
            for row in r:
                pos, cname, dtype, udt, null, default = row
                d = (default or "").replace("|", "\\|")
                if len(d) > 80:
                    d = d[:77] + "..."
                out(
                    f"| {pos} | `{cname}` | {dtype} | `{udt}` | {null} | {d or '—'} |"
                )
            out()

    out("## Application models in this repo (SQLAlchemy)")
    out()
    out(
        "The codebase under `app/models/` currently declares **`Property`** mapped to "
        "table **`properties`** (integer `id`, PostGIS `location`, JSON fields, etc.). "
        "The live database inspected here has **no `properties` table**; listings use "
        "**`properties_normalized`** and many other tables. Alembic revisions in "
        "`alembic/versions/` may not match `alembic_version` above if migrations are "
        "maintained elsewhere."
    )
    out()

    (ROOT / "db.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {ROOT / 'db.md'}")


if __name__ == "__main__":
    main()
