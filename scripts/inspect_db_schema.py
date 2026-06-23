"""Generate a safe database schema inventory from the configured backend .env.

This script intentionally avoids printing connection strings or credentials.
It is meant for Phase 0 discovery before schema-changing implementation work.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


IGNORED_SCHEMAS = {"information_schema"}


def _load_env(env_path: Path) -> None:
    if not env_path.exists():
        raise SystemExit(f"Environment file not found: {env_path}")
    load_dotenv(env_path)


def _build_database_url() -> URL | str:
    """Build a database URL without exposing the password in logs.

    Prefer individual DB_* fields because they safely handle special
    characters in passwords without requiring URL escaping.
    """
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if all([db_host, db_port, db_name, db_user, db_password]):
        return URL.create(
            "postgresql+psycopg2",
            username=db_user,
            password=db_password,
            host=db_host,
            port=int(db_port),
            database=db_name,
        )

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL or DB_* environment values are required")
    return database_url


def _connect_timeout() -> int:
    value = os.getenv("DB_CONNECT_TIMEOUT", "10")
    try:
        return int(value)
    except ValueError:
        return 10


def _create_engine():
    connect_args: dict[str, Any] = {"connect_timeout": _connect_timeout()}
    ssl_mode = os.getenv("DB_SSLMODE", "require")
    if ssl_mode:
        connect_args["sslmode"] = ssl_mode
    return create_engine(_build_database_url(), pool_pre_ping=True, connect_args=connect_args)


def _safe_error_message(exc: Exception) -> str:
    raw_message = str(exc).lower()
    if "password authentication failed" in raw_message or "authentication failed" in raw_message:
        return "Database authentication failed; verify credentials, username format, or auth method."
    if "timeout" in raw_message or "timed out" in raw_message:
        return "Database connection timed out; verify network access, firewall rules, and host settings."
    if "could not translate host name" in raw_message or "name or service not known" in raw_message:
        return "Database host could not be resolved; verify DB host settings."
    if "ssl" in raw_message:
        return "Database SSL negotiation failed; verify DB SSL mode and server requirements."
    return "Database schema inspection failed; verify connection settings and rerun."


def _column_payload(column: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": column["name"],
        "type": str(column["type"]),
        "nullable": bool(column.get("nullable")),
        "default": str(column.get("default")) if column.get("default") is not None else None,
        "primary_key": bool(column.get("primary_key")),
    }


def _list_extensions(connection) -> list[str]:
    result = connection.execute(text("select extname from pg_extension order by extname"))
    return [str(row[0]) for row in result]


def _list_enum_types(connection) -> list[dict[str, Any]]:
    result = connection.execute(
        text(
            """
            select t.typname, string_agg(e.enumlabel, ',' order by e.enumsortorder) as labels
            from pg_type t
            join pg_enum e on e.enumtypid = t.oid
            join pg_namespace n on n.oid = t.typnamespace
            where n.nspname = 'public'
            group by t.typname
            order by t.typname
            """
        )
    )
    return [
        {"name": str(row[0]), "labels": str(row[1]).split(",") if row[1] else []}
        for row in result
    ]


def _list_alembic_versions(connection, inspector) -> list[str]:
    if not inspector.has_table("alembic_version", schema="public"):
        return []
    result = connection.execute(text("select version_num from alembic_version order by version_num"))
    return [str(row[0]) for row in result]


def build_schema_inventory() -> dict[str, Any]:
    engine = _create_engine()
    with engine.connect() as connection:
        inspector = inspect(connection)
        db_name = connection.execute(text("select current_database()")).scalar()
        current_schema = connection.execute(text("select current_schema()")).scalar()
        version = connection.execute(text("select version()")).scalar()

        schemas = [
            schema
            for schema in inspector.get_schema_names()
            if schema not in IGNORED_SCHEMAS and not schema.startswith("pg_")
        ]

        inventory: dict[str, Any] = {
            "database": db_name,
            "current_schema": current_schema,
            "postgres_version": version,
            "extensions": _list_extensions(connection),
            "enum_types": _list_enum_types(connection),
            "alembic_versions": _list_alembic_versions(connection, inspector),
            "schemas": [],
        }

        for schema in schemas:
            schema_payload = {"name": schema, "tables": []}
            for table_name in inspector.get_table_names(schema=schema):
                table_payload = {
                    "name": table_name,
                    "columns": [_column_payload(column) for column in inspector.get_columns(table_name, schema=schema)],
                    "primary_key": inspector.get_pk_constraint(table_name, schema=schema),
                    "foreign_keys": inspector.get_foreign_keys(table_name, schema=schema),
                    "indexes": inspector.get_indexes(table_name, schema=schema),
                    "unique_constraints": inspector.get_unique_constraints(table_name, schema=schema),
                    "check_constraints": inspector.get_check_constraints(table_name, schema=schema),
                }
                schema_payload["tables"].append(table_payload)
            inventory["schemas"].append(schema_payload)

        return inventory


def write_markdown(inventory: dict[str, Any], output_path: Path) -> None:
    lines: list[str] = [
        "# Live Database Schema Inventory",
        "",
        f"Database: `{inventory['database']}`",
        f"Current schema: `{inventory['current_schema']}`",
        "",
    ]

    if inventory.get("alembic_versions"):
        lines.extend(["Alembic versions:", ""])
        for version in inventory["alembic_versions"]:
            lines.append(f"- `{version}`")
        lines.append("")

    if inventory.get("extensions"):
        lines.extend(["PostgreSQL extensions:", ""])
        for extension in inventory["extensions"]:
            lines.append(f"- `{extension}`")
        lines.append("")

    if inventory.get("enum_types"):
        lines.extend(["Enum types:", ""])
        for enum_type in inventory["enum_types"]:
            labels = ", ".join(f"`{label}`" for label in enum_type["labels"])
            lines.append(f"- `{enum_type['name']}`: {labels}")
        lines.append("")

    for schema in inventory["schemas"]:
        lines.extend([f"## Schema `{schema['name']}`", ""])
        if not schema["tables"]:
            lines.extend(["No tables discovered.", ""])
            continue

        for table in schema["tables"]:
            lines.extend([f"### `{schema['name']}.{table['name']}`", ""])
            lines.extend(["| Column | Type | Nullable | Default | PK |", "| --- | --- | --- | --- | --- |"])
            for column in table["columns"]:
                lines.append(
                    "| {name} | {type} | {nullable} | {default} | {primary_key} |".format(
                        name=column["name"],
                        type=column["type"],
                        nullable="yes" if column["nullable"] else "no",
                        default=column["default"] or "",
                        primary_key="yes" if column["primary_key"] else "",
                    )
                )
            lines.append("")

            if table["foreign_keys"]:
                lines.extend(["Foreign keys:", ""])
                for fk in table["foreign_keys"]:
                    constrained = ", ".join(fk.get("constrained_columns") or [])
                    referred_schema = fk.get("referred_schema") or schema["name"]
                    referred_table = fk.get("referred_table")
                    referred_cols = ", ".join(fk.get("referred_columns") or [])
                    lines.append(f"- `{constrained}` -> `{referred_schema}.{referred_table}({referred_cols})`")
                lines.append("")

            if table["indexes"]:
                lines.extend(["Indexes:", ""])
                for index in table["indexes"]:
                    columns = ", ".join(index.get("column_names") or [])
                    unique = " unique" if index.get("unique") else ""
                    lines.append(f"- `{index['name']}` on `{columns}`{unique}")
                lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_json(inventory: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect configured database schema")
    parser.add_argument("--env", default=".env", help="Path to backend .env file")
    parser.add_argument("--markdown", help="Markdown output path")
    parser.add_argument("--json", help="JSON output path")
    args = parser.parse_args()

    _load_env(Path(args.env))

    try:
        inventory = build_schema_inventory()
    except SQLAlchemyError as exc:
        print("db-schema-inspection-failed")
        print(exc.__class__.__name__)
        print(_safe_error_message(exc))
        return 1

    if args.markdown:
        write_markdown(inventory, Path(args.markdown))
    if args.json:
        write_json(inventory, Path(args.json))

    table_count = sum(len(schema["tables"]) for schema in inventory["schemas"])
    print("db-schema-inspection-ok")
    print(f"schemas={len(inventory['schemas'])}")
    print(f"tables={table_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
