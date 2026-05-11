"""
Backfill `properties_normalized.agent_user_id` for properties missing an agent assignment.

Distribution rules:
- Only updates rows where `agent_user_id IS NULL`
- Excludes soft-deleted properties (`deleted_at IS NULL`)
- Deterministic ordering by `property_hash` then `id`
- Even distribution across N agents:
    base = total // N
    remainder = total % N
    First `remainder` agents get (base + 1) properties, others get `base`.

This script is idempotent: rerunning will not change already-assigned rows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, bindparam, func, select, update

# Add project root so "app" can be imported when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.property_normalized import PropertyNormalized  # noqa: E402
from app.models.user import Role, User, user_roles  # noqa: E402
from app.utils.constants import UserRoles  # noqa: E402


DEFAULT_AGENT_IDS = [
    "0d5a75dc-fed9-4724-a80f-2b8952860b58",
    "4dcf0550-1534-477d-b4e2-70f1175fca54",
    "63079fac-c5d2-475b-9e60-d92a1c9fe65d",
    "6e22100d-99c0-483a-ad88-fda91cbc44a7",
    "9bd86fd3-e884-4102-a5f4-474f10ad4d3f",
    "b4df393d-fdf2-4151-be79-35bdcdbce268",
    "d2486ec8-44a7-43e7-8962-83c9764011e7",
    "d87a97af-d53e-43d7-9e9e-aa366048dfcb",
    "e27ea82a-a08f-4d85-8c5f-f34927fd90e4",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill missing properties_normalized.agent_user_id with a balanced distribution."
    )
    p.add_argument(
        "--agent-id",
        action="append",
        dest="agent_ids",
        help="Agent user UUID. Repeat flag to pass multiple (default: built-in 9 ids).",
    )
    p.add_argument(
        "--include-deleted",
        action="store_true",
        help="Also assign soft-deleted properties (default: excluded).",
    )
    p.add_argument(
        "--skip-role-check",
        action="store_true",
        help="Skip validating agents have roles.name='agent' (still validates user exists).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit how many missing-agent properties to update (0 = all).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute distribution but do not write anything.",
    )
    return p.parse_args()


def _validate_agents(*, db, agent_ids: list[UUID], skip_role_check: bool) -> None:
    if not agent_ids:
        raise ValueError("No agent ids provided.")

    existing_users = {
        row[0]
        for row in db.execute(select(User.id).where(User.id.in_(agent_ids))).all()
    }
    missing = [str(a) for a in agent_ids if a not in existing_users]
    if missing:
        raise ValueError(f"These agent ids do not exist in users: {', '.join(missing)}")

    if skip_role_check:
        return

    # Validate role 'agent' using RBAC tables.
    agent_role_users = {
        row[0]
        for row in db.execute(
            select(User.id)
            .select_from(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .join(Role, Role.id == user_roles.c.role_id)
            .where(
                and_(
                    User.id.in_(agent_ids),
                    Role.name == UserRoles.AGENT,
                    User.deleted_at.is_(None),
                )
            )
            .distinct()
        ).all()
    }
    not_agents = [str(a) for a in agent_ids if a not in agent_role_users]
    if not_agents:
        raise ValueError(
            "These user ids exist but do not have role 'agent' (or are deleted): "
            + ", ".join(not_agents)
        )


def _get_target_property_ids(*, db, include_deleted: bool, limit: int) -> list[UUID]:
    filters = [PropertyNormalized.agent_user_id.is_(None)]
    if not include_deleted:
        filters.append(PropertyNormalized.deleted_at.is_(None))

    stmt = (
        select(PropertyNormalized.id)
        .where(and_(*filters))
        .order_by(PropertyNormalized.property_hash.asc(), PropertyNormalized.id.asc())
    )
    if limit and limit > 0:
        stmt = stmt.limit(int(limit))

    return [row[0] for row in db.execute(stmt).all()]


def _count_missing(*, db, include_deleted: bool) -> int:
    filters = [PropertyNormalized.agent_user_id.is_(None)]
    if not include_deleted:
        filters.append(PropertyNormalized.deleted_at.is_(None))
    return int(
        db.execute(select(func.count()).select_from(PropertyNormalized).where(and_(*filters))).scalar()
        or 0
    )


def _distribution_counts(total: int, n_agents: int) -> list[int]:
    base = total // n_agents
    rem = total % n_agents
    return [(base + 1) if i < rem else base for i in range(n_agents)]


def backfill(
    *,
    agent_ids: list[UUID],
    include_deleted: bool,
    skip_role_check: bool,
    limit: int,
    dry_run: bool,
) -> dict[str, int]:
    with SessionLocal() as db:
        _validate_agents(db=db, agent_ids=agent_ids, skip_role_check=skip_role_check)

        missing_before = _count_missing(db=db, include_deleted=include_deleted)
        prop_ids = _get_target_property_ids(db=db, include_deleted=include_deleted, limit=limit)
        total = len(prop_ids)
        n_agents = len(agent_ids)

        if total == 0:
            if dry_run:
                db.rollback()
            return {
                "agents": n_agents,
                "properties_missing_agent": 0,
                "updates_intended": 0,
                "missing_before": missing_before,
                "missing_after": missing_before,
            }

        counts = _distribution_counts(total, n_agents)

        # Build updates deterministically: first K properties go to agent 0, next go to agent 1, etc.
        params: list[dict] = []
        idx = 0
        for agent_idx, agent_id in enumerate(agent_ids):
            c = counts[agent_idx]
            if c <= 0:
                continue
            chunk = prop_ids[idx : idx + c]
            idx += c
            params.extend({"id": pid, "b_id": pid, "agent_user_id": agent_id} for pid in chunk)

        if len(params) != total:
            raise RuntimeError(f"Internal error: expected {total} updates, built {len(params)}")

        stmt = (
            update(PropertyNormalized)
            .where(PropertyNormalized.id == bindparam("b_id"))
            .where(PropertyNormalized.agent_user_id.is_(None))  # safety: don't overwrite
            .values(agent_user_id=bindparam("agent_user_id"))
        )
        db.execute(stmt.execution_options(synchronize_session=False), params)

        if dry_run:
            db.rollback()
        else:
            db.commit()

        missing_after = missing_before if dry_run else _count_missing(db=db, include_deleted=include_deleted)
        updated = max(0, missing_before - missing_after)
        return {
            "agents": n_agents,
            "properties_missing_agent": total,
            "updates_intended": total,
            "missing_before": missing_before,
            "missing_after": missing_after,
            "properties_updated": updated,
        }


if __name__ == "__main__":
    args = _parse_args()
    raw_ids = args.agent_ids or DEFAULT_AGENT_IDS
    agent_ids = [UUID(str(x)) for x in raw_ids]

    out = backfill(
        agent_ids=agent_ids,
        include_deleted=bool(args.include_deleted),
        skip_role_check=bool(args.skip_role_check),
        limit=int(args.limit or 0),
        dry_run=bool(args.dry_run),
    )

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(
        f"[{mode}] agents={out['agents']} "
        f"properties_missing_agent={out['properties_missing_agent']} "
        f"updates_intended={out['updates_intended']} "
        f"properties_updated={out['properties_updated']} "
        f"missing_before={out['missing_before']} missing_after={out['missing_after']}"
    )
