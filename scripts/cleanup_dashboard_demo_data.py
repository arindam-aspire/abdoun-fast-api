"""Cleanup dashboard demo data seeded by seed_dashboard_demo_data.py.

Deletes **only** primary keys listed in the local manifest for that agent email.
IDs are recorded exclusively by the seed script; cleanup never uses broad deletes.

Also removes the **dashboard_summary** snapshot row for that agent (same ``user_id``)
so stale scheduler materialization does not linger after demo data is gone.

Manifest path:
  scripts/.dashboard_demo_seed_manifest.json

Examples:
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com --all-runs
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com --verify-markers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, or_, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.property_normalized import (
    ActivityLog,
    DashboardSummary,
    Lead,
    PropertyNormalized,
    PropertyView,
)
from app.models.user import User  # noqa: F401 - register User so mappers resolve (e.g. UserPropertyFavorite.user)

MANIFEST_PATH = Path(__file__).parent / ".dashboard_demo_seed_manifest.json"

# Must match seed_dashboard_demo_data.py markers (for optional safety check)
DEMO_INQUIRY_TYPE = "dashboard_demo_seed"
DEMO_ACTIVITY_TYPE = "dashboard_demo_seed"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"runs": []}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _to_uuid_list(values):
    return [UUID(v) for v in values]


def _count_rows_for_property(
    db,
    *,
    property_id: UUID,
    lead_ids: list[UUID],
    property_view_ids: list[UUID],
    activity_ids: list[UUID],
) -> tuple[int, int, int]:
    """How many manifest-tracked rows for this property still exist (before delete)."""
    nl = nv = na = 0
    if lead_ids:
        nl = db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.id.in_(lead_ids), Lead.property_id == property_id)
        ).scalar_one()
    if property_view_ids:
        nv = db.execute(
            select(func.count())
            .select_from(PropertyView)
            .where(PropertyView.id.in_(property_view_ids), PropertyView.property_id == property_id)
        ).scalar_one()
    if activity_ids:
        na = db.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.id.in_(activity_ids), ActivityLog.property_id == property_id)
        ).scalar_one()
    return int(nl), int(nv), int(na)


def _print_cleanup_plan(db, target_runs: list) -> None:
    """Describe what will be removed (mirrors seed script layout)."""
    n_runs = len(target_runs)
    print()
    print("Removing tracked rows per manifest run:")
    print("-" * 60)
    for run_idx, run in enumerate(target_runs, start=1):
        seeded_at = run.get("seeded_at", "(unknown)")
        ids = run.get("ids", {})
        lead_uuids = _to_uuid_list(ids.get("leads", []))
        view_uuids = _to_uuid_list(ids.get("property_views", []))
        act_uuids = _to_uuid_list(ids.get("activity_logs", []))
        property_ids_raw = run.get("property_ids") or []

        print(f"  Run [{run_idx}/{n_runs}]  seeded_at (UTC): {seeded_at}")

        if not property_ids_raw:
            total_l = len(lead_uuids)
            total_v = len(view_uuids)
            total_a = len(act_uuids)
            print(
                "      (manifest has no property_ids; deleting by id lists only)"
                f"  leads: {total_l}  |  property_views: {total_v}  |  activity_logs: {total_a}"
            )
            continue

        prop_count = len(property_ids_raw)
        for idx, pid_str in enumerate(property_ids_raw):
            pid = UUID(pid_str)
            nl, nv, na = _count_rows_for_property(
                db,
                property_id=pid,
                lead_ids=lead_uuids,
                property_view_ids=view_uuids,
                activity_ids=act_uuids,
            )
            prop = db.get(PropertyNormalized, pid)
            title = ((prop.title if prop else None) or "(unknown)")[:72]
            print(f"      [{idx + 1}/{prop_count}] {title}")
            print(f"          property_id: {pid}")
            print(f"          + leads: {nl}  |  property_views: {nv}  |  activity_logs: {na}")
    print("-" * 60)


def _verify_demo_markers(db, lead_ids: list[UUID], activity_ids: list[UUID]) -> None:
    """Abort if manifest ids point at rows that are not demo-marked (safety)."""
    if lead_ids:
        bad_leads = db.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.id.in_(lead_ids),
                or_(Lead.inquiry_type.is_(None), Lead.inquiry_type != DEMO_INQUIRY_TYPE),
            )
        ).scalar_one()
        if int(bad_leads or 0) > 0:
            raise RuntimeError(
                f"Refusing delete: {bad_leads} lead row(s) do not have "
                f"inquiry_type={DEMO_INQUIRY_TYPE!r}. Manifest may be stale or IDs corrupted."
            )
    if activity_ids:
        bad_act = db.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.id.in_(activity_ids),
                or_(ActivityLog.activity_type.is_(None), ActivityLog.activity_type != DEMO_ACTIVITY_TYPE),
            )
        ).scalar_one()
        if int(bad_act or 0) > 0:
            raise RuntimeError(
                f"Refusing delete: {bad_act} activity_log row(s) do not have "
                f"activity_type={DEMO_ACTIVITY_TYPE!r}."
            )


def cleanup_dashboard_data(agent_email: str, *, all_runs: bool = False, verify_markers: bool = False) -> None:
    manifest = _load_manifest()
    runs = manifest.get("runs", [])
    matching_runs = [run for run in runs if run.get("agent_email") == agent_email]
    if not matching_runs:
        print(f"No manifest runs found for agent email: {agent_email}")
        return

    target_runs = matching_runs if all_runs else [matching_runs[-1]]

    lead_ids = []
    property_view_ids = []
    activity_ids = []
    synthetic_property_ids: list[UUID] = []
    for run in target_runs:
        ids = run.get("ids", {})
        lead_ids.extend(_to_uuid_list(ids.get("leads", [])))
        property_view_ids.extend(_to_uuid_list(ids.get("property_views", [])))
        activity_ids.extend(_to_uuid_list(ids.get("activity_logs", [])))
        synthetic_property_ids.extend(_to_uuid_list(run.get("synthetic_property_ids", [])))

    agent_user_id = target_runs[-1].get("agent_user_id") if target_runs else None

    resolved_user_id = None
    deleted_leads = 0
    deleted_property_views = 0
    deleted_activities = 0
    deleted_synthetic_properties = 0
    deleted_dashboard_summary = 0

    db = SessionLocal()
    try:
        user_row = db.execute(select(User).where(User.email == agent_email)).scalar_one_or_none()
        resolved_user_id = user_row.id if user_row else None

        _print_cleanup_plan(db, target_runs)

        if verify_markers:
            _verify_demo_markers(db, lead_ids, activity_ids)
            print("  Marker check: all manifest leads/activity_logs match demo seed markers.")

        if lead_ids:
            result = db.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
            deleted_leads = result.rowcount or 0
        if property_view_ids:
            result = db.execute(delete(PropertyView).where(PropertyView.id.in_(property_view_ids)))
            deleted_property_views = result.rowcount or 0
        if activity_ids:
            result = db.execute(delete(ActivityLog).where(ActivityLog.id.in_(activity_ids)))
            deleted_activities = result.rowcount or 0

        if synthetic_property_ids:
            result = db.execute(
                delete(PropertyNormalized).where(PropertyNormalized.id.in_(synthetic_property_ids))
            )
            deleted_synthetic_properties = result.rowcount or 0

        summary_uid = resolved_user_id
        if summary_uid is None and agent_user_id:
            try:
                summary_uid = UUID(str(agent_user_id))
            except ValueError:
                summary_uid = None
        if summary_uid is not None:
            result = db.execute(
                delete(DashboardSummary).where(DashboardSummary.user_id == summary_uid)
            )
            deleted_dashboard_summary = result.rowcount or 0

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    remaining_runs = [run for run in runs if run not in target_runs]
    _save_manifest({"runs": remaining_runs})

    runs_removed = len(target_runs)
    scope = "all matching runs" if all_runs else "latest run only"

    print("Dashboard demo cleanup complete.")
    print(f"  Agent email:          {agent_email}")
    if resolved_user_id:
        print(f"  Agent user id:       {resolved_user_id}")
    elif agent_user_id:
        print(f"  Agent user id:       {agent_user_id} (from manifest)")
    print(f"  Manifest runs scope: {scope}")
    print(f"  Runs removed:         {runs_removed}")
    print(f"  Leads deleted:        {deleted_leads}")
    print(f"  Property views:       {deleted_property_views}")
    print(f"  Activity logs:        {deleted_activities}")
    if synthetic_property_ids:
        print(f"  Synthetic properties:  {deleted_synthetic_properties}")
    print(f"  dashboard_summary rows: {deleted_dashboard_summary} (for this agent user_id)")
    print(f"  Manifest updated:     {MANIFEST_PATH.resolve()}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup dashboard demo seeded data.")
    parser.add_argument("--agent-email", required=True, help="Agent email used in seed run")
    parser.add_argument(
        "--all-runs",
        action="store_true",
        help="Delete all tracked runs for this agent (default deletes latest run only).",
    )
    parser.add_argument(
        "--verify-markers",
        action="store_true",
        help=(
            "Before DELETE, ensure manifest lead/activity rows still have demo inquiry_type "
            "and activity_type (abort if not)."
        ),
    )
    args = parser.parse_args()
    cleanup_dashboard_data(args.agent_email, all_runs=args.all_runs, verify_markers=args.verify_markers)


if __name__ == "__main__":
    main()

