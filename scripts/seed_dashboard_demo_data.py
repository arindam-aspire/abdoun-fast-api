"""Seed demo data for agent dashboard summary metrics.

Modes:
  * Legacy / date-range: seed leads, views, activity on existing agent listings.
  * --mtd-percentage-targets: insert synthetic listings + rows so MoM %% match
    ~15.6 / 7.5 / 5.0 / 4.4 (aligned MTD windows, same rounding as the API).

Examples:
  python scripts/seed_dashboard_demo_data.py --agent-email agent@example.com
  python scripts/seed_dashboard_demo_data.py --agent-email a@b.com --spread-days 45
  python scripts/seed_dashboard_demo_data.py --agent-email a@b.com \\
      --event-start 2026-03-01 --event-end 2026-04-23
  python scripts/seed_dashboard_demo_data.py --agent-email a@b.com --mtd-percentage-targets
  python scripts/seed_dashboard_demo_data.py --agent-email a@b.com \\
      --mtd-percentage-targets --mtd-variant negative
  python scripts/seed_dashboard_demo_data.py --agent-email a@b.com \\
      --mtd-percentage-targets --mtd-variant mixed --mtd-isolate

Cleanup inserted rows + synthetic properties (manifest):
  python scripts/cleanup_dashboard_demo_data.py --agent-email agent@example.com
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.property_normalized import ActivityLog, Lead, PropertyNormalized, PropertyStatus, PropertyView
from app.models.user import User
from app.schemas.property import uuid_to_int_hash

MANIFEST_PATH = Path(__file__).parent / ".dashboard_demo_seed_manifest.json"
DEMO_INQUIRY_TYPE = "dashboard_demo_seed"
DEMO_ACTIVITY_TYPE = "dashboard_demo_seed"
DEMO_MESSAGE_PREFIX = "[DASHBOARD_DEMO]"

# Range mode: more leads/views so prev vs current MTD windows both get counts
RANGE_LEADS_PER_PROPERTY = 8
RANGE_VIEWS_MIN = 6
RANGE_VIEWS_MAX = 12

# --- MTD % calibration (matches AgentDashboardService._mom_percent_change rounding) ---
@dataclass(frozen=True)
class MTDCalibrationProfile:
    """Integer prev/curr window counts so MoM %% matches targets after Decimal half-up to 0.1."""

    listings_prev: int
    listings_curr: int
    leads_prev: int
    leads_curr: int
    deals_prev: int
    deals_curr: int
    views_prev: int
    views_curr: int
    activity_feed: int = 5
    variant: str = "positive"  # "positive" | "negative" | "mixed"


def _mom_preview(curr: int, prev: int) -> float:
    """Same rounding as AgentDashboardService._mom_percent_change."""
    if prev == 0:
        return 0.0 if curr == 0 else 100.0
    raw = ((curr - prev) / prev) * 100
    return float(Decimal(str(raw)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


# Positive MoM: ~15.6 / 7.5 / 5.0 / 4.4
MTD_PROFILE_POSITIVE = MTDCalibrationProfile(
    listings_prev=64,
    listings_curr=74,
    leads_prev=40,
    leads_curr=43,
    deals_prev=20,
    deals_curr=21,
    views_prev=91,
    views_curr=95,
    activity_feed=5,
    variant="positive",
)

# Negative MoM: curr < prev (e.g. deals -5.0 == (19-20)/20*100)
MTD_PROFILE_NEGATIVE = MTDCalibrationProfile(
    listings_prev=80,
    listings_curr=60,
    leads_prev=83,
    leads_curr=63,
    deals_prev=20,
    deals_curr=19,
    views_prev=100,
    views_curr=89,
    activity_feed=5,
    variant="negative",
)

# Mixed per-axis MoM: +25 / -24.1 / +5 / -11 (same rounding as API)
MTD_PROFILE_MIXED = MTDCalibrationProfile(
    listings_prev=80,
    listings_curr=100,
    leads_prev=83,
    leads_curr=63,
    deals_prev=20,
    deals_curr=21,
    views_prev=100,
    views_curr=89,
    activity_feed=5,
    variant="mixed",
)

MTD_PROFILES_BY_VARIANT: dict[str, MTDCalibrationProfile] = {
    "positive": MTD_PROFILE_POSITIVE,
    "negative": MTD_PROFILE_NEGATIVE,
    "mixed": MTD_PROFILE_MIXED,
}

# Far outside any aligned-MTD window so existing agent rows do not affect demo counts
_MTD_ISOLATE_ANCHOR_TS = datetime(1970, 1, 1, 0, 0, 0)


def _mtd_isolate_existing_agent_properties(db, user_id) -> int:
    """Move all listings for this agent out of MTD windows (destructive; demo/local only).

    Dashboard listing/deal metrics count every row with agent_user_id. Without this,
    real listings pollute counts (e.g. deals +5% instead of -5%).
    """
    result = db.execute(
        update(PropertyNormalized)
        .where(PropertyNormalized.agent_user_id == user_id)
        .values(
            created_at=_MTD_ISOLATE_ANCHOR_TS,
            updated_at=_MTD_ISOLATE_ANCHOR_TS,
            deal_closed=False,
        )
    )
    return int(result.rowcount or 0)


def _aligned_mtd_bounds(now_utc: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """Same window logic as app.repositories.agent_dashboard_repository._aligned_mtd_bounds."""
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        prev_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_start = month_start.replace(month=month_start.month - 1)
    prev_end = prev_start + (now_utc - month_start)
    return month_start, now_utc, prev_start, prev_end


def _prop_ts_naive(dt: datetime) -> datetime:
    """TIMESTAMP columns on PropertyNormalized: store as naive UTC."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rand_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = max((end - start).total_seconds(), 1.0)
    return start + timedelta(seconds=rng.uniform(0, span))


def _clone_demo_property(
    template: PropertyNormalized,
    *,
    agent_user_id,
    title: str,
    created_at: datetime,
    updated_at: datetime,
    deal_closed: bool,
) -> PropertyNormalized:
    pid = uuid4()
    prop = PropertyNormalized(
        id=pid,
        property_hash=uuid_to_int_hash(pid),
        category_id=template.category_id,
        type_id=template.type_id,
        property_status_id=template.property_status_id,
        city_id=template.city_id,
        location_id=template.location_id,
        url=None,
        title=title[:500],
        description=template.description,
        is_exclusive=template.is_exclusive,
        is_featured=template.is_featured,
        is_verified=template.is_verified,
        latitude=template.latitude,
        longitude=template.longitude,
        location=template.location,
        location_name=template.location_name,
        reference_number=None,
        price=template.price,
        currency=template.currency,
        selling_price_amount=template.selling_price_amount,
        selling_price_currency=template.selling_price_currency,
        rent_price_amount=template.rent_price_amount,
        rent_price_currency=template.rent_price_currency,
        rent_commission_percent=template.rent_commission_percent,
        contract_duration=template.contract_duration,
        payment_method=template.payment_method,
        area=template.area,
        plot_area=template.plot_area,
        bedrooms=template.bedrooms,
        bathrooms=template.bathrooms,
        rooms=template.rooms,
        furniture_status=template.furniture_status,
        parking=template.parking,
        property_age=template.property_age,
        images=template.images if template.images is not None else "[]",
        virtual_tour_url=template.virtual_tour_url,
        more_features=template.more_features,
        agent_user_id=agent_user_id,
        created_by=template.created_by,
        updated_by_user_id=template.updated_by_user_id,
        approved_by_user_id=template.approved_by_user_id,
        deal_closed=deal_closed,
        created_at=_prop_ts_naive(created_at),
        updated_at=_prop_ts_naive(updated_at),
    )
    return prop


def _seed_mtd_percentage_targets(
    db,
    user: User,
    template: PropertyNormalized,
    now_utc: datetime,
    rng: random.Random,
    agent_email: str,
    profile: MTDCalibrationProfile,
) -> dict:
    """Insert synthetic rows so aligned-MTD deltas match the chosen profile (positive or negative MoM)."""
    cs, ce, ps, pe = _aligned_mtd_bounds(now_utc)

    ids_out = {"leads": [], "property_views": [], "activity_logs": []}
    synthetic_property_ids: list[str] = []
    all_props: list[PropertyNormalized] = []

    lp, lc = profile.listings_prev, profile.listings_curr
    dp, dc = profile.deals_prev, profile.deals_curr

    print()
    print("MTD calibrated seed (synthetic listings + leads/views/deals timestamps)")
    print(f"  Variant: {profile.variant} (curr vs prev window counts drive MoM sign)")
    print(f"  Aligned windows (UTC): curr [{cs.isoformat()} .. {ce.isoformat()}]")
    print(f"                         prev [{ps.isoformat()} .. {pe.isoformat()}]")
    print("-" * 60)

    # --- Listings: created_at in prev vs curr windows
    prev_rows: list[PropertyNormalized] = []
    curr_rows: list[PropertyNormalized] = []
    for i in range(lp):
        ca = _rand_between(rng, ps, pe)
        ua = ca
        p = _clone_demo_property(
            template,
            agent_user_id=user.id,
            title=f"[DEMO_MTDLIST] Prev {i + 1}/{lp}",
            created_at=_aware_utc(ca),
            updated_at=_aware_utc(ua),
            deal_closed=False,
        )
        db.add(p)
        prev_rows.append(p)
        synthetic_property_ids.append(str(p.id))
        all_props.append(p)
    for i in range(lc):
        ca = _rand_between(rng, cs, ce)
        ua = ca
        p = _clone_demo_property(
            template,
            agent_user_id=user.id,
            title=f"[DEMO_MTDLIST] Curr {i + 1}/{lc}",
            created_at=_aware_utc(ca),
            updated_at=_aware_utc(ua),
            deal_closed=False,
        )
        db.add(p)
        curr_rows.append(p)
        synthetic_property_ids.append(str(p.id))
        all_props.append(p)

    db.flush()

    # --- Deals: closed + updated_at in prev / curr windows (subset of listing clones)
    for p in prev_rows[:dp]:
        p.deal_closed = True
        p.updated_at = _prop_ts_naive(_rand_between(rng, ps, pe))
    for p in curr_rows[:dc]:
        p.deal_closed = True
        p.updated_at = _prop_ts_naive(_rand_between(rng, cs, ce))

    pool_ids = [p.id for p in all_props]

    def pick_prop(i: int):
        return pool_ids[i % len(pool_ids)]

    # --- Leads
    for _ in range(profile.leads_prev):
        lid = uuid4()
        ts = _aware_utc(_rand_between(rng, ps, pe))
        db.add(
            Lead(
                id=lid,
                property_id=pick_prop(len(ids_out["leads"])),
                user_id=user.id,
                inquiry_type=DEMO_INQUIRY_TYPE,
                message=f"{DEMO_MESSAGE_PREFIX} MTD-prev lead",
                created_at=ts,
                updated_at=ts,
            )
        )
        ids_out["leads"].append(str(lid))
    for _ in range(profile.leads_curr):
        lid = uuid4()
        ts = _aware_utc(_rand_between(rng, cs, ce))
        db.add(
            Lead(
                id=lid,
                property_id=pick_prop(len(ids_out["leads"])),
                user_id=user.id,
                inquiry_type=DEMO_INQUIRY_TYPE,
                message=f"{DEMO_MESSAGE_PREFIX} MTD-curr lead",
                created_at=ts,
                updated_at=ts,
            )
        )
        ids_out["leads"].append(str(lid))

    # --- Property views
    for _ in range(profile.views_prev):
        vid = uuid4()
        ts = _aware_utc(_rand_between(rng, ps, pe))
        db.add(
            PropertyView(
                id=vid,
                property_id=pick_prop(len(ids_out["property_views"])),
                user_type="registered",
                user_id=user.id,
                viewed_at=ts,
                created_at=ts,
                updated_at=ts,
            )
        )
        ids_out["property_views"].append(str(vid))
    for _ in range(profile.views_curr):
        vid = uuid4()
        ts = _aware_utc(_rand_between(rng, cs, ce))
        db.add(
            PropertyView(
                id=vid,
                property_id=pick_prop(len(ids_out["property_views"])),
                user_type="registered",
                user_id=user.id,
                viewed_at=ts,
                created_at=ts,
                updated_at=ts,
            )
        )
        ids_out["property_views"].append(str(vid))

    # --- Recent activity (small feed inside current window)
    for i in range(profile.activity_feed):
        aid = uuid4()
        ts = _aware_utc(_rand_between(rng, cs, ce))
        pid = pick_prop(i)
        db.add(
            ActivityLog(
                id=aid,
                user_id=user.id,
                property_id=pid,
                activity_type=DEMO_ACTIVITY_TYPE,
                message=f"{DEMO_MESSAGE_PREFIX} MTD activity {i + 1}",
                tone="success" if i % 2 == 0 else "info",
                created_at=ts,
                updated_at=ts,
            )
        )
        ids_out["activity_logs"].append(str(aid))

    print(
        f"  Synthetic properties: {len(synthetic_property_ids)} "
        f"(listings prev {lp} / curr {lc}; deals flagged {dp}+{dc})"
    )
    print(
        f"  Leads: {profile.leads_prev}+{profile.leads_curr} | "
        f"Views: {profile.views_prev}+{profile.views_curr} | Activity: {profile.activity_feed}"
    )
    ex_l = _mom_preview(lc, lp)
    ex_ld = _mom_preview(profile.leads_curr, profile.leads_prev)
    ex_d = _mom_preview(dc, dp)
    ex_v = _mom_preview(profile.views_curr, profile.views_prev)
    print(
        f"  Expected *ChangePercent: listings {ex_l} | leads {ex_ld} | deals {ex_d} | views {ex_v}"
    )
    print("-" * 60)

    return {
        "seeded_at": now_utc.isoformat(),
        "seed_mode": "mtd_percentage_targets",
        "mtd_variant": profile.variant,
        "agent_email": agent_email,
        "agent_user_id": str(user.id),
        "property_ids": [str(template.id)],
        "synthetic_property_ids": synthetic_property_ids,
        "ids": ids_out,
        "mtd_windows_utc": {"cs": cs.isoformat(), "ce": ce.isoformat(), "ps": ps.isoformat(), "pe": pe.isoformat()},
    }


def _get_or_create_status_ids(db) -> tuple[int, int]:
    active = db.execute(
        select(PropertyStatus).where(PropertyStatus.slug == "active")
    ).scalar_one_or_none()
    draft = db.execute(
        select(PropertyStatus).where(PropertyStatus.slug == "draft")
    ).scalar_one_or_none()

    if active is None:
        active = PropertyStatus(name="Active", slug="active", is_active=True)
        db.add(active)
        db.flush()
    if draft is None:
        draft = PropertyStatus(name="Draft", slug="draft", is_active=True)
        db.add(draft)
        db.flush()
    return active.id, draft.id


def _resolve_agent_properties(
    db, user_id, active_status_id: int, draft_status_id: int, count: int
) -> tuple[list, bool]:
    """Return (properties, used_fallback) where used_fallback means unassigned rows were claimed."""
    properties = db.execute(
        select(PropertyNormalized)
        .where(PropertyNormalized.agent_user_id == user_id)
        .order_by(PropertyNormalized.created_at.desc())
        .limit(count)
    ).scalars().all()
    if properties:
        return properties, False

    print("No properties assigned to this agent; assigning recent unassigned properties for demo...")
    candidates = db.execute(
        select(PropertyNormalized)
        .where(PropertyNormalized.agent_user_id.is_(None))
        .order_by(PropertyNormalized.created_at.desc())
        .limit(count)
    ).scalars().all()
    for idx, prop in enumerate(candidates):
        prop.agent_user_id = user_id
        prop.property_status_id = active_status_id if idx % 3 else draft_status_id
        prop.deal_closed = idx % 4 == 0
    return candidates, True


def _property_rng(prop: PropertyNormalized, idx: int) -> random.Random:
    """Stable RNG per property so repeated seeds are reproducible."""
    seed = int(hashlib.sha256(f"{prop.id}:{idx}".encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _utc_day_start(date_str: str) -> datetime:
    """Parse YYYY-MM-DD as start of that day in UTC."""
    dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _utc_day_end(date_str: str) -> datetime:
    """Parse YYYY-MM-DD as end of that day in UTC (inclusive)."""
    start = _utc_day_start(date_str)
    return start.replace(hour=23, minute=59, second=59, microsecond=999999)


def _dt_uniform(rng: random.Random, start: datetime, end: datetime) -> datetime:
    if end <= start:
        return start
    span = (end - start).total_seconds()
    return start + timedelta(seconds=rng.uniform(0, span))


def _seed_events_legacy(db, user_id, prop: PropertyNormalized, idx: int, now: datetime) -> dict:
    """Original behaviour: fixed day offsets from now (last ~30 days)."""
    created = {"leads": [], "property_views": [], "activity_logs": []}

    for day_offset in (1, 3, 8, 15, 22, 29):
        created_at = now - timedelta(days=day_offset, hours=idx)
        lead_id = uuid4()
        db.add(
            Lead(
                id=lead_id,
                property_id=prop.id,
                user_id=user_id,
                inquiry_type=DEMO_INQUIRY_TYPE,
                message=f"{DEMO_MESSAGE_PREFIX} Demo inquiry {idx + 1}",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        created["leads"].append(str(lead_id))

    rng = _property_rng(prop, idx)
    for _ in range(rng.randint(3, 8)):
        viewed_at = now - timedelta(days=rng.randint(0, 12), hours=rng.randint(0, 23))
        view_id = uuid4()
        db.add(
            PropertyView(
                id=view_id,
                property_id=prop.id,
                user_type="registered",
                user_id=user_id,
                viewed_at=viewed_at,
                created_at=viewed_at,
                updated_at=viewed_at,
            )
        )
        created["property_views"].append(str(view_id))

    activity_at = now - timedelta(minutes=(idx + 1) * 12)
    activity_id = uuid4()
    db.add(
        ActivityLog(
            id=activity_id,
            user_id=user_id,
            property_id=prop.id,
            activity_type=DEMO_ACTIVITY_TYPE,
            message=f"{DEMO_MESSAGE_PREFIX} New inquiry on {prop.title}.",
            tone="success" if idx % 2 == 0 else "info",
            created_at=activity_at,
            updated_at=activity_at,
        )
    )
    created["activity_logs"].append(str(activity_id))
    return created


def _seed_events_date_range(
    db,
    user_id,
    prop: PropertyNormalized,
    idx: int,
    range_start: datetime,
    range_end: datetime,
) -> dict:
    """Place leads/views/activity timestamps uniformly/randomly inside [range_start, range_end] (UTC)."""
    created = {"leads": [], "property_views": [], "activity_logs": []}
    rng = _property_rng(prop, idx)

    span = max((range_end - range_start).total_seconds(), 1.0)

    # Leads: one per equal slice of the range so both "early" and "late" periods get rows
    for i in range(RANGE_LEADS_PER_PROPERTY):
        slice_start = range_start + timedelta(seconds=span * (i / RANGE_LEADS_PER_PROPERTY))
        slice_end = range_start + timedelta(seconds=span * ((i + 1) / RANGE_LEADS_PER_PROPERTY))
        created_at = _dt_uniform(rng, slice_start, slice_end)

        lead_id = uuid4()
        db.add(
            Lead(
                id=lead_id,
                property_id=prop.id,
                user_id=user_id,
                inquiry_type=DEMO_INQUIRY_TYPE,
                message=f"{DEMO_MESSAGE_PREFIX} Demo inquiry {idx + 1} ({i + 1}/{RANGE_LEADS_PER_PROPERTY})",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        created["leads"].append(str(lead_id))

    n_views = rng.randint(RANGE_VIEWS_MIN, RANGE_VIEWS_MAX)
    for _ in range(n_views):
        viewed_at = _dt_uniform(rng, range_start, range_end)
        view_id = uuid4()
        db.add(
            PropertyView(
                id=view_id,
                property_id=prop.id,
                user_type="registered",
                user_id=user_id,
                viewed_at=viewed_at,
                created_at=viewed_at,
                updated_at=viewed_at,
            )
        )
        created["property_views"].append(str(view_id))

    # Activity: toward end of window but still inside range (feeds "recent activity")
    tail_start = range_start + timedelta(seconds=span * 0.72)
    activity_at = _dt_uniform(rng, tail_start, range_end)
    activity_id = uuid4()
    db.add(
        ActivityLog(
            id=activity_id,
            user_id=user_id,
            property_id=prop.id,
            activity_type=DEMO_ACTIVITY_TYPE,
            message=f"{DEMO_MESSAGE_PREFIX} New inquiry on {prop.title}.",
            tone="success" if idx % 2 == 0 else "info",
            created_at=activity_at,
            updated_at=activity_at,
        )
    )
    created["activity_logs"].append(str(activity_id))
    return created


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"runs": []}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": []}


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _resolve_event_range(
    *,
    event_start: str | None,
    event_end: str | None,
    spread_days: int | None,
    now: datetime,
) -> tuple[datetime, datetime] | None:
    """Return inclusive UTC range for event timestamps, or None for legacy seed."""
    if event_start and event_end:
        rs = _utc_day_start(event_start)
        re_ = _utc_day_end(event_end)
        if re_ < rs:
            raise ValueError("--event-end must be on or after --event-start")
        return rs, re_
    if spread_days is not None:
        if spread_days < 1:
            raise ValueError("--spread-days must be >= 1")
        end = now
        start = now - timedelta(days=float(spread_days))
        return start, end
    return None


def seed_dashboard_data(
    agent_email: str,
    count: int = 6,
    *,
    event_start: str | None = None,
    event_end: str | None = None,
    spread_days: int | None = None,
    mtd_percentage_targets: bool = False,
    mtd_variant: str = "positive",
    mtd_isolate: bool = False,
) -> None:
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == agent_email)).scalar_one_or_none()
        if user is None:
            print(f"Agent user not found for email: {agent_email}")
            return

        now = datetime.now(timezone.utc)

        if mtd_percentage_targets:
            profile = MTD_PROFILES_BY_VARIANT.get(mtd_variant, MTD_PROFILE_POSITIVE)
            active_status_id, draft_status_id = _get_or_create_status_ids(db)
            tpl_props, used_fb = _resolve_agent_properties(
                db,
                user.id,
                active_status_id=active_status_id,
                draft_status_id=draft_status_id,
                count=1,
            )
            if not tpl_props:
                print("No template property found for MTD calibration (need at least one listing or fallback pool).")
                db.rollback()
                return
            isolated_n = 0
            if mtd_isolate:
                isolated_n = _mtd_isolate_existing_agent_properties(db, user.id)
                db.flush()
                db.refresh(tpl_props[0])
                print(
                    f"  MTD isolate: reset created_at/updated_at + deal_closed on "
                    f"{isolated_n} existing row(s) for this agent (1970-01-01 UTC)."
                )
                print("    (Avoids mixing real listings into aligned-MTD demo counts.)")
            rng = random.Random(42)
            run_manifest = _seed_mtd_percentage_targets(
                db, user, tpl_props[0], now, rng, agent_email=agent_email, profile=profile
            )
            run_manifest["mtd_isolated"] = bool(mtd_isolate)
            if mtd_isolate:
                run_manifest["mtd_isolated_rowcount"] = isolated_n
            db.commit()
            manifest = _load_manifest()
            manifest.setdefault("runs", []).append(run_manifest)
            _save_manifest(manifest)
            _mtd_labels = {
                "positive": "positive MoM",
                "negative": "negative MoM",
                "mixed": "mixed MoM (+25 / -24.1 / +5 / -11)",
            }
            label = _mtd_labels.get(profile.variant, "MTD MoM")
            print(f"Dashboard demo seed complete (MTD percentage targets - {label}).")
            print(f"  Agent email:           {agent_email}")
            print(f"  Agent user id:         {user.id}")
            print(f"  Synthetic properties:  {len(run_manifest.get('synthetic_property_ids', []))}")
            print(f"  Leads / views / logs:  {len(run_manifest['ids']['leads'])}/"
                  f"{len(run_manifest['ids']['property_views'])}/{len(run_manifest['ids']['activity_logs'])}")
            print(f"  Manifest updated:       {MANIFEST_PATH.resolve()}")
            if used_fb:
                print("  Note: template property came from unassigned-property fallback.")
            print()
            return

        event_range = _resolve_event_range(
            event_start=event_start,
            event_end=event_end,
            spread_days=spread_days,
            now=now,
        )

        active_status_id, draft_status_id = _get_or_create_status_ids(db)
        properties, used_fallback = _resolve_agent_properties(
            db,
            user.id,
            active_status_id=active_status_id,
            draft_status_id=draft_status_id,
            count=count,
        )

        if not properties:
            print("No properties available to seed dashboard data.")
            db.rollback()
            return

        run_manifest: dict = {
            "seeded_at": now.isoformat(),
            "seed_mode": "date_range" if event_range else "legacy",
            "agent_email": agent_email,
            "agent_user_id": str(user.id),
            "property_ids": [str(p.id) for p in properties],
            "ids": {
                "leads": [],
                "property_views": [],
                "activity_logs": [],
            },
        }
        if event_range:
            rs, re_ = event_range
            run_manifest["event_date_range_utc"] = {
                "start": rs.isoformat(),
                "end": re_.isoformat(),
            }

        print()
        print("Seeding per property:")
        if event_range:
            rs, re_ = event_range
            print(f"  Event window (UTC): {rs.isoformat()}  ->  {re_.isoformat()}")
        else:
            print("  Mode: legacy (~30-day offsets from now)")
        print("-" * 60)
        for idx, prop in enumerate(properties):
            if event_range:
                rs, re_ = event_range
                created = _seed_events_date_range(db, user.id, prop, idx, rs, re_)
            else:
                created = _seed_events_legacy(db, user.id, prop, idx, now)
            run_manifest["ids"]["leads"].extend(created["leads"])
            run_manifest["ids"]["property_views"].extend(created["property_views"])
            run_manifest["ids"]["activity_logs"].extend(created["activity_logs"])
            nl = len(created["leads"])
            nv = len(created["property_views"])
            na = len(created["activity_logs"])
            title = (prop.title or "(no title)")[:72]
            print(f"  [{idx + 1}/{len(properties)}] {title}")
            print(f"      property_id: {prop.id}")
            print(f"      + leads: {nl}  |  property_views: {nv}  |  activity_logs: {na}")

        db.commit()
        manifest = _load_manifest()
        manifest.setdefault("runs", []).append(run_manifest)
        _save_manifest(manifest)

        total_leads = len(run_manifest["ids"]["leads"])
        total_views = len(run_manifest["ids"]["property_views"])
        total_activity = len(run_manifest["ids"]["activity_logs"])

        print("-" * 60)
        print("Dashboard demo seed complete.")
        print(f"  Agent email:       {agent_email}")
        print(f"  Agent user id:     {user.id}")
        print(f"  Properties used:   {len(properties)}")
        print(f"  Seed mode:         {run_manifest['seed_mode']}")
        if event_range:
            rs, re_ = event_range
            print(f"  Event range (UTC): {rs.date()} .. {re_.date()}")
        if used_fallback:
            print("  Note:              Used unassigned properties and linked them to this agent.")
        print(f"  Leads created:     {total_leads}")
        print(f"  Property views:    {total_views}")
        print(f"  Activity logs:     {total_activity}")
        print(f"  Seeded at (UTC):   {run_manifest['seeded_at']}")
        print(f"  Manifest updated:  {MANIFEST_PATH.resolve()}")
        print()
    except Exception as exc:
        db.rollback()
        print(f"Failed to seed dashboard demo data: {exc}")
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed dashboard demo data (tracked in scripts/.dashboard_demo_seed_manifest.json)."
    )
    parser.add_argument("--agent-email", required=True, help="Agent email to seed data for")
    parser.add_argument("--count", type=int, default=6, help="Max properties to use")
    range_group = parser.add_argument_group(
        "Event date range (UTC, optional)",
        "Use explicit dates OR --spread-days. Omit all for legacy ~30-day behaviour.",
    )
    range_group.add_argument(
        "--event-start",
        metavar="YYYY-MM-DD",
        help="Inclusive start calendar day (UTC) for leads/views/activity timestamps",
    )
    range_group.add_argument(
        "--event-end",
        metavar="YYYY-MM-DD",
        help="Inclusive end calendar day (UTC) for leads/views/activity timestamps",
    )
    range_group.add_argument(
        "--spread-days",
        type=int,
        metavar="N",
        help="Spread events from now minus N days through now (UTC). Typical: 45-50 for MTD testing.",
    )
    parser.add_argument(
        "--mtd-percentage-targets",
        action="store_true",
        help=(
            "Insert synthetic listings + leads/views/deals sized so listings/leads/deals/views "
            "MoM %% match the chosen --mtd-variant (aligned MTD windows, same math as the API)."
        ),
    )
    parser.add_argument(
        "--mtd-variant",
        choices=("positive", "negative", "mixed"),
        default="positive",
        help=(
            "With --mtd-percentage-targets: positive ~= 15.6/7.5/5.0/4.4; "
            "negative ~= listings/deals down; mixed = +25 listings, -24.1 leads, +5 deals, -11 views."
        ),
    )
    parser.add_argument(
        "--mtd-isolate",
        action="store_true",
        help=(
            "With --mtd-percentage-targets: before inserting synthetics, set ALL this agent's "
            "existing properties to created_at/updated_at 1970-01-01 UTC and deal_closed=false "
            "so MoM %% match the profile (destructive to dates; local demo only)."
        ),
    )
    args = parser.parse_args()

    if (args.event_start or args.event_end) and not (args.event_start and args.event_end):
        parser.error("--event-start and --event-end must be used together")

    if args.spread_days is not None and (args.event_start or args.event_end):
        parser.error("Use either (--event-start AND --event-end) OR --spread-days, not both")

    if args.mtd_percentage_targets:
        if args.event_start or args.event_end or args.spread_days is not None:
            parser.error("--mtd-percentage-targets cannot be combined with date-range options")

    if args.mtd_variant != "positive" and not args.mtd_percentage_targets:
        parser.error("--mtd-variant only applies with --mtd-percentage-targets")

    if args.mtd_isolate and not args.mtd_percentage_targets:
        parser.error("--mtd-isolate only applies with --mtd-percentage-targets")

    seed_dashboard_data(
        args.agent_email,
        max(1, args.count),
        event_start=args.event_start,
        event_end=args.event_end,
        spread_days=args.spread_days,
        mtd_percentage_targets=args.mtd_percentage_targets,
        mtd_variant=args.mtd_variant,
        mtd_isolate=args.mtd_isolate,
    )


if __name__ == "__main__":
    main()
