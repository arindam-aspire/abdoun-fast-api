#!/usr/bin/env python3
"""
Production-safe PostgreSQL data sync: Local → Production.

- Does NOT modify schema or alembic_version.
- Uses COPY for bulk transfer (no ORM, no row-by-row inserts).
- Idempotent: SAFE_MODE=True skips non-empty target tables; SAFE_MODE=False truncates then copies.
- Run with DRY_RUN=1 to log actions without executing.

Requires: psycopg2-binary, python-dotenv

Config is read from .env (project root). Same variable names as the app for local DB.

  Local (existing): DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
  Production (add to .env): PROD_DB_USER, PROD_DB_PASSWORD, PROD_DB_HOST, PROD_DB_PORT, PROD_DB_NAME
  Example for me-south-1: PROD_DB_HOST=your-rds.me-south-1.rds.amazonaws.com
  Or set PRODUCTION_DATABASE_URL to override (full URL).

Optional: DRY_RUN=1, SAFE_MODE=1 (default), LOG_LEVEL=INFO.

IMPORTANT - Alembic: You MUST run `alembic upgrade head` on the production DB *before*
running this script. This script only syncs data; it does not run migrations. It checks
that alembic_version matches on both DBs and aborts if not.

Usage:
  # 1. Ensure production schema is up to date (run once from your machine or CI)
  alembic upgrade head  # with production DATABASE_URL or PROD_* in .env

  # 2. Dry run (no writes)
  DRY_RUN=1 python scripts/sync_data_to_production.py

  # 3. Safe sync (only copy into empty target tables)
  python scripts/sync_data_to_production.py

  # 4. Full replace (truncate data tables on production then copy)
  SAFE_MODE=0 python scripts/sync_data_to_production.py
"""

from __future__ import annotations

import io
import logging
import os
import sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from urllib.parse import quote_plus

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection as PgConnection

from dotenv import load_dotenv

# Load .env from project root (parent of scripts/)
_env_dir = Path(__file__).resolve().parent.parent
load_dotenv(_env_dir / ".env")

# -----------------------------------------------------------------------------
# Configuration from environment (same names as app .env)
# -----------------------------------------------------------------------------
from urllib.parse import quote_plus, unquote
import os


def getenv_clean(key: str, default: str = "") -> str:
    """
    Read env variable and clean quotes/spaces.
    Works with values like:
    DB_PASSWORD="Swati%40123"
    """
    value = os.getenv(key, default)

    if value is None:
        return default

    value = value.strip()

    # remove quotes if present
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]

    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]

    return value



# -----------------------
# Flags
# -----------------------

DRY_RUN = getenv_clean("DRY_RUN", "0").lower() in ("1", "true", "yes")
SAFE_MODE = getenv_clean("SAFE_MODE", "1").lower() in ("1", "true", "yes")
LOG_LEVEL = getattr(logging, getenv_clean("LOG_LEVEL", "INFO").upper(), logging.INFO)

def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


# SQLAlchemy-style URL is accepted; we convert to psycopg2 (replace +psycopg2 if present)
def _normalize_database_url(url: str) -> str:
    if not url:
        return ""
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def _build_url(user: str, password: str, host: str, port: str, dbname: str) -> str:
    """Build postgresql:// URL with password safely quoted."""
    if not all([user, host, dbname]):
        return ""
    safe_password = quote_plus(password) if password else ""
    port_part = f":{port}" if port else ""
    return f"postgresql://{quote_plus(user)}:{safe_password}@{host}{port_part}/{quote_plus(dbname)}"



# -----------------------
# Local Database
# -----------------------

LOCAL_URL = _build_url(
    getenv_clean("DB_USER"),
    getenv_clean("DB_PASSWORD"),
    getenv_clean("DB_HOST"),
    getenv_clean("DB_PORT"),
    getenv_clean("DB_NAME"),
)


# -----------------------
# Production Database
# -----------------------

PRODUCTION_URL = _build_url(
    getenv_clean("PROD_DB_USER"),
    getenv_clean("PROD_DB_PASSWORD"),
    getenv_clean("PROD_DB_HOST"),
    getenv_clean("PROD_DB_PORT"),
    getenv_clean("PROD_DB_NAME"),
)


# # Local DB: from DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME (or LOCAL_DATABASE_URL / DATABASE_URL)
# _local_from_parts = _build_url(
#     _env("DB_USER"),
#     _env("DB_PASSWORD"),
#     _env("DB_HOST"),
#     _env("DB_PORT"),
#     _env("DB_NAME"),
# )
# LOCAL_URL = _normalize_database_url(
#     _env("LOCAL_DATABASE_URL") or _env("DATABASE_URL") or _local_from_parts
# )

# # Production DB: from PROD_DB_USER, PROD_DB_PASSWORD, PROD_DB_HOST, PROD_DB_PORT, PROD_DB_NAME (or PRODUCTION_DATABASE_URL)
# _prod_from_parts = _build_url(
#     _env("PROD_DB_USER"),
#     _env("PROD_DB_PASSWORD"),
#     _env("PROD_DB_HOST"),
#     _env("PROD_DB_PORT"),
#     _env("PROD_DB_NAME"),
# )
# PRODUCTION_URL = _normalize_database_url(
#     _env("PRODUCTION_DATABASE_URL") or _prod_from_parts
# )

DRY_RUN = _env("DRY_RUN", "0").lower() in ("1", "true", "yes")
SAFE_MODE = _env("SAFE_MODE", "1").lower() in ("1", "true", "yes")
LOG_LEVEL = getattr(logging, _env("LOG_LEVEL", "INFO").upper(), logging.INFO)

# Tables we never touch (schema/metadata)
SKIP_TABLES = frozenset({"alembic_version"})

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Connection helpers
# -----------------------------------------------------------------------------
@contextmanager
def connect(url: str, label: str) -> Generator[PgConnection, None, None]:
    """Open a psycopg2 connection with autocommit=False (transactions)."""
    if not url:
        raise ValueError(f"{label} database URL is not set")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        log.info("Connected to %s", label)
        yield conn
    finally:
        conn.close()
        log.info("Disconnected from %s", label)


def get_alembic_version(conn: PgConnection) -> str | None:
    """Return current alembic version or None if table missing/empty."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT version_num FROM alembic_version
            ORDER BY version_num DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        return row[0] if row else None

def get_public_tables_in_dependency_order(conn: PgConnection) -> list[str]:
    """
    Deterministic dependency order for Abdoun schema.
    Parents appear before children to avoid FK violations during COPY.
    """

    TABLE_ORDER = [
        # Base tables
        "cities",
        "areas",

        # Category must exist BEFORE types
        "property_categories",

        # Independent lookup tables
        "property_status",
        "features",
        "search_fields",

        # Dependent on property_categories
        "property_types",

        # Relationship tables
        "category_features",
        "category_search_fields",
        "type_features",

        # Main property table
        "properties_normalized",

        # Property relations
        "property_features",
        "property_translations",
        "property_media",
    ]

    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
        """)
        existing = {r[0] for r in cur.fetchall()}

    ordered = [t for t in TABLE_ORDER if t in existing]

    log.info("Using deterministic table order for sync")
    return ordered

    
def table_row_count(conn: PgConnection, table: str) -> int:
    """Return number of rows in table (safe quoted identifier)."""
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
        )
        return cur.fetchone()[0]


def copy_table_from_to(
    src_conn: PgConnection,
    dst_conn: PgConnection,
    table: str,
    dry_run: bool,
) -> int:
    """
    Transfer table data from source to destination using COPY.
    Returns number of rows transferred (0 if dry run).
    """
    buffer = io.StringIO()
    with src_conn.cursor() as cur_src:
        # COPY table TO STDOUT uses native column order; no SELECT * reordering
        copy_sql = sql.SQL("COPY {} TO STDOUT").format(sql.Identifier(table))
        if dry_run:
            log.info("[DRY_RUN] Would run on source: %s", copy_sql.as_string(cur_src))
            return 0
        cur_src.copy_expert(copy_sql, buffer)
    buffer.seek(0)
    # COPY text format: one line per row (trailing newline per row)
    row_count = buffer.getvalue().count("\n")

    with dst_conn.cursor() as cur_dst:
        copy_sql = sql.SQL("COPY {} FROM STDIN").format(sql.Identifier(table))
        if dry_run:
            log.info("[DRY_RUN] Would run on dest: %s (%s rows)", copy_sql.as_string(cur_dst), row_count)
            return 0
        cur_dst.copy_expert(copy_sql, buffer)
    return row_count


def truncate_table(conn: PgConnection, table: str, dry_run: bool) -> None:
    """Truncate a single table (no CASCADE). Call in reverse dependency order if needed."""
    with conn.cursor() as cur:
        stmt = sql.SQL("TRUNCATE TABLE {}").format(sql.Identifier(table))
        if dry_run:
            log.info("[DRY_RUN] Would run: %s", stmt.as_string(cur))
            return
        cur.execute(stmt)


def run_sync() -> None:
    """Main sync: verify alembic, then copy tables in dependency order."""
    if not LOCAL_URL:
        log.error(
            "Local DB URL not set. Set DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME "
            "in .env (or LOCAL_DATABASE_URL / DATABASE_URL)."
        )
        sys.exit(1)
    if not PRODUCTION_URL:
        log.error(
            "Production DB URL not set. Set PROD_DB_USER, PROD_DB_PASSWORD, PROD_DB_HOST, "
            "PROD_DB_PORT, PROD_DB_NAME in .env (or PRODUCTION_DATABASE_URL)."
        )
        sys.exit(1)
    if DRY_RUN:
        log.warning("DRY_RUN is enabled; no changes will be made")

    with connect(LOCAL_URL, "local") as local_conn, connect(
        PRODUCTION_URL, "production"
    ) as prod_conn:
        # Step 1: Verify alembic_version matches (we do not modify it)
        local_ver = get_alembic_version(local_conn)
        prod_ver = get_alembic_version(prod_conn)
        log.info("Local alembic version: %s", local_ver)
        log.info("Production alembic version: %s", prod_ver)
        if local_ver != prod_ver:
            log.error(
                "alembic_version mismatch (local=%s, production=%s). Aborting.",
                local_ver,
                prod_ver,
            )
            sys.exit(1)

        # Step 2: Table order for COPY (parents before children)
        tables = get_public_tables_in_dependency_order(local_conn)
        log.info("Tables to consider (in COPY order): %s", tables)

        # Truncation order on production: reverse of COPY order (children first)
        truncate_order = list(reversed(tables))

        if not SAFE_MODE and not DRY_RUN:
            for table in truncate_order:
                truncate_table(prod_conn, table, dry_run=DRY_RUN)
            prod_conn.commit()
            log.info("Truncated all data tables on production (SAFE_MODE=False)")

        total_rows = 0
        for table in tables:
            src_count = table_row_count(local_conn, table)
            if src_count == 0:
                log.info("Skipping %s (empty on source)", table)
                continue
            dst_count = table_row_count(prod_conn, table)
            if SAFE_MODE and dst_count > 0:
                log.info(
                    "Skipping %s (target has %s rows; SAFE_MODE=True)",
                    table,
                    dst_count,
                )
                continue
            # When SAFE_MODE=False we already truncated all tables above
            log.info("Copying %s (%s rows from source)", table, src_count)
            try:
                n = copy_table_from_to(local_conn, prod_conn, table, dry_run=DRY_RUN)
                total_rows += n
                if not DRY_RUN:
                    prod_conn.commit()
            except Exception as e:
                log.exception("Failed to copy table %s: %s", table, e)
                prod_conn.rollback()
                raise

        log.info("Sync complete. Total rows transferred: %s", total_rows)


if __name__ == "__main__":
    try:
        run_sync()
    except Exception as e:
        log.exception("Sync failed: %s", e)
        sys.exit(1)
