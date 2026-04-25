"""Cleanup dashboard demo data seeded by seed_dashboard_demo_data.py.

Deletes **only** primary keys listed in the local manifest for that agent email.
IDs are recorded exclusively by the seed script; cleanup never uses broad deletes.

Also:
  * Restores ``created_at`` / ``updated_at`` / ``deal_closed`` on rows that were
    MTD-isolated (``mtd_isolation_snapshots`` in the manifest).
  * Releases unassigned catalogue rows claimed for demo (``unassigned_claim_snapshots``),
    setting ``agent_user_id`` back to NULL and restoring prior status/deal flags.

The agent dashboard API recomputes ``totalProperties`` / deals from live
``properties_normalized`` rows; without these steps, counts stay inflated after
demo-only rows are deleted.

Also removes the **dashboard_summary** snapshot row for that agent (same ``user_id``)
so stale scheduler materialization does not linger after demo data is gone.

Manifest path:
  scripts/.dashboard_demo_seed_manifest.json

Examples:
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com --all-runs
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com --verify-markers

If the local manifest is missing (e.g. seed ran on another machine), use:
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com --purge-residual-demo

Tables touched by seed (see review / script docs): ``leads``, ``property_views``,
``activity_logs``, ``properties_normalized`` (inserts and sometimes updates),
``dashboard_summary`` (indirectly inflated; cleanup removes the agent snapshot row),
and optionally new rows in ``property_status`` (slug ``active`` / ``draft``) if they
did not already exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, or_, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.property_normalized import (
    ActivityLog,
    DashboardSummary,
    Lead,
    PropertyFeature,
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


def _parse_manifest_datetime(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    s = value.replace("Z", "+00:00") if value.endswith("Z") else value
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _runs_sorted_by_seeded_at(runs: list[dict]) -> list[dict]:
    return sorted(runs, key=lambda r: r.get("seeded_at") or "")


def _merged_mtd_isolation_snapshots(runs: list[dict]) -> list[dict]:
    """Oldest run wins per property_id (true pre-demo timestamps)."""
    merged: dict[str, dict] = {}
    for run in _runs_sorted_by_seeded_at(runs):
        for snap in run.get("mtd_isolation_snapshots") or []:
            pid = snap.get("property_id")
            if pid and pid not in merged:
                merged[pid] = snap
    return list(merged.values())


def _legacy_claim_snapshots_from_property_ids(run: dict) -> list[dict]:
    """Manifests before unassigned_claim_snapshots existed (fallback-only hint)."""
    if not run.get("used_unassigned_fallback"):
        return []
    return [
        {"property_id": pid, "property_status_id": None, "deal_closed": False}
        for pid in run.get("property_ids", [])
    ]


def _merged_unassigned_claim_snapshots(runs: list[dict]) -> list[dict]:
    """Oldest run wins per property_id (pre-claim pool state)."""
    merged: dict[str, dict] = {}
    for run in _runs_sorted_by_seeded_at(runs):
        snaps = run.get("unassigned_claim_snapshots")
        if not snaps and run.get("used_unassigned_fallback"):
            snaps = _legacy_claim_snapshots_from_property_ids(run)
        if not snaps:
            continue
        for snap in snaps:
            pid = snap.get("property_id")
            if pid and pid not in merged:
                merged[pid] = snap
    return list(merged.values())


def _restore_mtd_isolation_snapshots(db, snapshots: list[dict], agent_uuid: UUID | None) -> int:
    if not snapshots or agent_uuid is None:
        return 0
    n = 0
    for snap in snapshots:
        pid = UUID(snap["property_id"])
        prop = db.get(PropertyNormalized, pid)
        if prop is None or prop.agent_user_id != agent_uuid:
            continue
        ca = _parse_manifest_datetime(snap.get("created_at"))
        ua = _parse_manifest_datetime(snap.get("updated_at"))
        if ca is not None:
            prop.created_at = ca
        if ua is not None:
            prop.updated_at = ua
        prop.deal_closed = bool(snap.get("deal_closed", False))
        n += 1
    return n


def _release_unassigned_claims(db, runs: list[dict], agent_uuid: UUID | None) -> int:
    """Clear agent_user_id on catalogue rows claimed only for demo seeding."""
    if agent_uuid is None:
        return 0
    merged = _merged_unassigned_claim_snapshots(runs)
    n = 0
    for snap in merged:
        pid = UUID(snap["property_id"])
        prop = db.get(PropertyNormalized, pid)
        if prop is None or prop.agent_user_id != agent_uuid:
            continue
        psid = snap.get("property_status_id")
        prop.agent_user_id = None
        if psid is not None:
            prop.property_status_id = psid
        if "deal_closed" in snap:
            prop.deal_closed = bool(snap["deal_closed"])
        n += 1
    return n


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


def _mtd_synthetic_property_predicate():
    """MTD seed uses these title/reference patterns (see _clone_demo_property / _seed_mtd)."""
    return or_(
        PropertyNormalized.title.like("[DEMO_MTDLIST]%"),
        PropertyNormalized.reference_number.like("DMTD-%"),
    )


def purge_residual_demo_data(agent_email: str, *, verify_markers: bool = False) -> None:
    """Remove demo rows without relying on ``.dashboard_demo_seed_manifest.json``.

    Use when the manifest is missing, corrupt, or was never copied from the machine
    that ran the seed. This handles:

    * ``leads`` with ``inquiry_type='dashboard_demo_seed'`` for this user
    * ``activity_logs`` with ``activity_type='dashboard_demo_seed'`` for this user
    * MTD synthetic ``properties_normalized`` rows (title ``[DEMO_MTDLIST]%`` or
      ``reference_number`` ``DMTD-%``) owned by this agent, plus ``property_views``
      and ``property_features`` pointing at those properties

    Does **not** remove ``property_views`` from legacy/date-range seeding on real
    listings (those rows are not distinguishable without the manifest). Does **not**
    restore unassigned catalogue rows or MTD-isolated timestamps (manifest required).
    """
    db = SessionLocal()
    deleted_leads_marker = 0
    deleted_activity_marker = 0
    deleted_views_synth = 0
    deleted_features_synth = 0
    deleted_leads_on_synth = 0
    deleted_activity_on_synth = 0
    deleted_synthetic_properties = 0
    deleted_dashboard_summary = 0
    try:
        user_row = db.execute(select(User).where(User.email == agent_email)).scalar_one_or_none()
        if user_row is None:
            print(f"No user found for email: {agent_email}")
            return
        uid = user_row.id

        lead_ids_marker = db.execute(select(Lead.id).where(Lead.user_id == uid, Lead.inquiry_type == DEMO_INQUIRY_TYPE)).scalars().all()
        act_ids_marker = db.execute(
            select(ActivityLog.id).where(
                ActivityLog.user_id == uid, ActivityLog.activity_type == DEMO_ACTIVITY_TYPE
            )
        ).scalars().all()
        if verify_markers and lead_ids_marker:
            _verify_demo_markers(db, list(lead_ids_marker), list(act_ids_marker))
            print("  Marker check: all candidate leads/activity_logs match demo seed markers.")

        if lead_ids_marker:
            r = db.execute(delete(Lead).where(Lead.id.in_(lead_ids_marker)))
            deleted_leads_marker = r.rowcount or 0
        if act_ids_marker:
            r = db.execute(delete(ActivityLog).where(ActivityLog.id.in_(act_ids_marker)))
            deleted_activity_marker = r.rowcount or 0

        synth_rows = db.execute(
            select(PropertyNormalized.id).where(
                PropertyNormalized.agent_user_id == uid,
                _mtd_synthetic_property_predicate(),
            )
        ).scalars().all()
        synth_ids = list(synth_rows)
        if synth_ids:
            r = db.execute(delete(PropertyView).where(PropertyView.property_id.in_(synth_ids)))
            deleted_views_synth = r.rowcount or 0
            r = db.execute(delete(PropertyFeature).where(PropertyFeature.property_id.in_(synth_ids)))
            deleted_features_synth = r.rowcount or 0
            r = db.execute(delete(Lead).where(Lead.property_id.in_(synth_ids)))
            deleted_leads_on_synth = r.rowcount or 0
            r = db.execute(delete(ActivityLog).where(ActivityLog.property_id.in_(synth_ids)))
            deleted_activity_on_synth = r.rowcount or 0
            r = db.execute(delete(PropertyNormalized).where(PropertyNormalized.id.in_(synth_ids)))
            deleted_synthetic_properties = r.rowcount or 0

        r = db.execute(delete(DashboardSummary).where(DashboardSummary.user_id == uid))
        deleted_dashboard_summary = r.rowcount or 0

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("Residual demo purge complete (no manifest).")
    print(f"  Agent email:              {agent_email}")
    print(f"  Leads (marker, user_id):  {deleted_leads_marker}")
    print(f"  Activity (marker, user_id): {deleted_activity_marker}")
    print(f"  Property views (synth):   {deleted_views_synth}")
    print(f"  Property features (synth): {deleted_features_synth}")
    print(f"  Leads (on synth props):   {deleted_leads_on_synth}")
    print(f"  Activity (on synth props): {deleted_activity_on_synth}")
    print(f"  Synthetic properties:     {deleted_synthetic_properties}")
    print(f"  dashboard_summary rows:   {deleted_dashboard_summary}")
    print()
    print(
        "If you used unassigned-property fallback or --mtd-isolate, reconcile manually "
        "or restore from backup unless you still have a manifest for cleanup_dashboard_data()."
    )
    print()


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
    restored_mtd_rows = 0
    released_claim_rows = 0

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

        if resolved_user_id is not None:
            mtd_snaps = _merged_mtd_isolation_snapshots(target_runs)
            restored_mtd_rows = _restore_mtd_isolation_snapshots(db, mtd_snaps, resolved_user_id)
            released_claim_rows = _release_unassigned_claims(db, target_runs, resolved_user_id)

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
    print(f"  MTD timestamps restored:  {restored_mtd_rows} (pre-isolate snapshot)")
    print(f"  Unassigned claims released: {released_claim_rows} (agent_user_id cleared)")
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
    parser.add_argument(
        "--purge-residual-demo",
        action="store_true",
        help=(
            "Do not use the manifest: delete demo-marker leads/activity for this user, "
            "purge MTD synthetic properties (title/reference patterns), then remove "
            "dashboard_summary for this user. For legacy seed views on real listings, "
            "run manifest-based cleanup if you still have .dashboard_demo_seed_manifest.json."
        ),
    )
    args = parser.parse_args()
    if args.purge_residual_demo:
        if args.all_runs:
            parser.error("--purge-residual-demo cannot be combined with --all-runs")
        purge_residual_demo_data(args.agent_email, verify_markers=args.verify_markers)
        return
    cleanup_dashboard_data(args.agent_email, all_runs=args.all_runs, verify_markers=args.verify_markers)


if __name__ == "__main__":
    main()

