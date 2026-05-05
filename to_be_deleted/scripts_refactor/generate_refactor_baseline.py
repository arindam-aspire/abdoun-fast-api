"""Generate baseline artifacts for the refactor effort."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import engine
from app.main import app
from app.models import Base

REFACTOR_DIR = ROOT / "docs" / "refactor"


DOMAINS = [
    "Auth & profile",
    "Users & RBAC",
    "Agents",
    "Admin dashboard",
    "Properties",
    "Geo search/import",
    "Taxonomy",
    "Submissions",
    "Agent property list",
    "Favorites",
    "Saved searches",
    "Recent views",
    "Uploads",
    "Owners",
    "Admin property assignment",
    "Observability",
    "Schedulers",
    "Scripts/data workflows",
]


def _ensure_dir() -> None:
    REFACTOR_DIR.mkdir(parents=True, exist_ok=True)


def _export_openapi() -> None:
    target = REFACTOR_DIR / "openapi_legacy_baseline.json"
    target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")


def _export_db_schema() -> None:
    payload: dict[str, Any] = {"tables": {}, "source": "database_inspect"}
    try:
        with engine.connect() as conn:
            column_rows = conn.execute(
                text(
                    """
                    SELECT
                        table_name,
                        column_name,
                        data_type,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                    """
                )
            ).mappings().all()
            for row in column_rows:
                table_name = row["table_name"]
                payload["tables"].setdefault(table_name, {"columns": []})
                payload["tables"][table_name]["columns"].append(
                    {
                        "column_name": row["column_name"],
                        "data_type": row["data_type"],
                        "is_nullable": row["is_nullable"],
                        "column_default": row["column_default"],
                    }
                )
    except OperationalError as exc:
        payload["source"] = "sqlalchemy_metadata_fallback"
        payload["error"] = str(exc)
        for table_name, table in sorted(Base.metadata.tables.items()):
            payload["tables"][table_name] = {
                "columns": [
                    {
                        "name": col.name,
                        "type": str(col.type),
                        "nullable": col.nullable,
                        "primary_key": col.primary_key,
                    }
                    for col in table.columns
                ],
                "primary_key": [col.name for col in table.primary_key.columns],
                "foreign_keys": [
                    {"column": fk.parent.name, "target": str(fk.target_fullname)}
                    for fk in table.foreign_keys
                ],
                "indexes": [idx.name for idx in table.indexes],
            }
        _write_blocker(
            "Task 01: DB schema export used metadata fallback because the "
            "configured database was unreachable."
        )

    target = REFACTOR_DIR / "db_schema_legacy_baseline.json"
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _build_route_inventory() -> None:
    from fastapi.routing import APIRoute

    routes: list[dict[str, Any]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        auth_dependencies: list[str] = []
        for dep in route.dependant.dependencies:
            call = dep.call
            if call is None:
                continue
            module_name = getattr(call, "__module__", call.__class__.__module__)
            callable_name = getattr(call, "__name__", call.__class__.__name__)
            auth_dependencies.append(f"{module_name}.{callable_name}")

        routes.append(
            {
                "name": route.name,
                "path": route.path,
                "methods": sorted(route.methods or []),
                "response_model": (
                    f"{route.response_model.__module__}.{route.response_model.__name__}"
                    if route.response_model is not None
                    else None
                ),
                "auth_dependencies": sorted(set(auth_dependencies)),
                "tags": route.tags,
            }
        )

    routes.sort(key=lambda item: (item["path"], ",".join(item["methods"])))
    target = REFACTOR_DIR / "ROUTE_INVENTORY.json"
    target.write_text(json.dumps(routes, indent=2), encoding="utf-8")


def _build_coverage_checklist() -> None:
    lines = [
        "# Functionality Coverage Checklist",
        "",
        "Track migration and parity status per domain.",
        "",
    ]
    for domain in DOMAINS:
        lines.extend(
            [
                f"## {domain}",
                "",
                "- [ ] Legacy behavior inventoried",
                "- [ ] Refactored implementation created",
                "- [ ] Parity tests added",
                "- [ ] Parity tests passing",
                "- [ ] Switched via startup flag",
                "",
            ]
        )

    target = REFACTOR_DIR / "FUNCTIONALITY_COVERAGE_CHECKLIST.md"
    target.write_text("\n".join(lines), encoding="utf-8")


def _write_blocker(message: str) -> None:
    target = REFACTOR_DIR / "BLOCKERS.md"
    existing = target.read_text(encoding="utf-8") if target.exists() else "# Blockers\n\n"
    if message not in existing:
        existing = existing.rstrip() + f"\n- {message}\n"
    target.write_text(existing, encoding="utf-8")


def main() -> None:
    _ensure_dir()
    _export_openapi()
    _export_db_schema()
    _build_route_inventory()
    _build_coverage_checklist()
    print("Baseline artifacts generated in docs/refactor/")


if __name__ == "__main__":
    main()
