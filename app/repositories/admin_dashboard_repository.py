"""Read-only SQL for platform admin dashboard (global aggregates)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.constants import UserRoles


def _property_performance_time_filter_sql(period: str) -> str:
    """Trailing window on ``property_views.viewed_at`` (timestamptz).

    Uses ``NOW() - interval`` so both sides stay ``timestamptz``. Avoid
    ``(NOW() AT TIME ZONE 'UTC')`` on the RHS: that yields ``timestamp`` and
    Postgres then applies ``TimeZone`` when coercing, which skews cutoffs in
    non-UTC sessions.

    ``all``: no lower bound (every view row).
    """
    if period == "all":
        return ""
    if period == "weekly":
        return " AND pv.viewed_at >= (NOW() - interval '7 days')"
    if period == "monthly":
        return " AND pv.viewed_at >= (NOW() - interval '30 days')"
    if period == "yearly":
        return " AND pv.viewed_at >= (NOW() - interval '365 days')"
    raise ValueError(f"Invalid property performance period: {period!r}")


def _shift_calendar_month(y: int, m: int, delta: int) -> tuple[int, int]:
    """Add delta months to (y, m); month in 1..12."""
    total = y * 12 + (m - 1) + delta
    ny, rem = divmod(total, 12)
    return ny, rem + 1


def _month_start_utc(y: int, m: int) -> datetime:
    return datetime(y, m, 1, tzinfo=timezone.utc)


@dataclass
class PropertyPerformanceRow:
    property_id: UUID
    agent_user_id: Optional[UUID]
    agent_name: str
    category_name: Optional[str]
    type_name: Optional[str]
    type_slug: Optional[str]
    area_or_location: str
    title: Optional[str]
    view_count: int


@dataclass
class KpiRawSnapshot:
    """Per reporting month vs full previous month (for MoM), plus listing snapshot KPIs."""

    month_label: str  # YYYY-MM
    users_curr: int
    users_prev: int
    agents_curr: int
    agents_prev: int
    listings_curr: int
    listings_prev: int
    leads_curr: int
    leads_prev: int
    deals_curr: int
    deals_prev: int
    pending_approvals: int
    pending_approvals_today: int


@dataclass
class TrendsRaw:
    month_labels: List[str]
    user_growth_series: List[int]
    listing_growth_series: List[int]
    lead_growth_series: List[int]
    months: int


@dataclass
class ActivityLogItem:
    text: str
    tone: str
    activity_at: datetime


class AdminDashboardRepository:
    """Analytics queries for admin dashboard (global scope)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _utc_day_bounds(self, now_utc: datetime) -> tuple[datetime, datetime]:
        day0 = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        return day0, day0 + timedelta(days=1)

    def fetch_kpis(
        self,
        *,
        year: int,
        month: int,
        now_utc: Optional[datetime] = None,
    ) -> KpiRawSnapshot:
        """Scalar KPIs for a full calendar month in UTC, plus previous full month; pending counts are snapshots.

        Note on "users" KPI:
        - `usersThisMonth` counts only `registered_user` role users (not admins/agents).
        - Excludes only deleted users (`users.deleted_at IS NULL`); includes inactive users.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        now_utc = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
        if not (1 <= month <= 12) or not (2000 <= year <= 2100):
            raise ValueError("Invalid calendar month for KPIs")
        month_start = _month_start_utc(year, month)
        if month == 12:
            next_start = _month_start_utc(year + 1, 1)
        else:
            next_start = _month_start_utc(year, month + 1)
        prev_y, prev_m = _shift_calendar_month(year, month, -1)
        prev_start = _month_start_utc(prev_y, prev_m)
        # Previous full month: [prev_start, month_start)
        today_start, tomorrow_start = self._utc_day_bounds(now_utc)

        row = self._db.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(DISTINCT u.id)::int
                     FROM users u
                     INNER JOIN user_roles ur ON ur.user_id = u.id
                     INNER JOIN roles r ON r.id = ur.role_id AND r.name = :registered_role
                     WHERE u.created_at >= :ms AND u.created_at < :mee
                       AND u.deleted_at IS NULL) AS u_curr,
                    (SELECT COUNT(DISTINCT u.id)::int
                     FROM users u
                     INNER JOIN user_roles ur ON ur.user_id = u.id
                     INNER JOIN roles r ON r.id = ur.role_id AND r.name = :registered_role
                     WHERE u.created_at >= :pms AND u.created_at < :pme
                       AND u.deleted_at IS NULL) AS u_prev,
                    (SELECT COUNT(DISTINCT ur.user_id)::int
                     FROM user_roles ur
                     INNER JOIN roles r ON r.id = ur.role_id AND r.name = :agent_role
                     WHERE ur.assigned_at >= :ms AND ur.assigned_at < :mee) AS ag_curr,
                    (SELECT COUNT(DISTINCT ur.user_id)::int
                     FROM user_roles ur
                     INNER JOIN roles r ON r.id = ur.role_id AND r.name = :agent_role
                     WHERE ur.assigned_at >= :pms AND ur.assigned_at < :pme) AS ag_prev,
                    (SELECT COUNT(*)::int FROM properties_normalized p
                     WHERE p.created_at >= :ms AND p.created_at < :mee) AS l_curr,
                    (SELECT COUNT(*)::int FROM properties_normalized p
                     WHERE p.created_at >= :pms AND p.created_at < :pme) AS l_prev,
                    (SELECT COUNT(l.id)::int FROM leads l
                     WHERE l.created_at >= :ms AND l.created_at < :mee) AS ld_curr,
                    (SELECT COUNT(l.id)::int FROM leads l
                     WHERE l.created_at >= :pms AND l.created_at < :pme) AS ld_prev,
                    (SELECT COUNT(*)::int FROM properties_normalized p
                     WHERE COALESCE(p.deal_closed, false) = true
                       AND p.updated_at >= :ms AND p.updated_at < :mee) AS d_curr,
                    (SELECT COUNT(*)::int FROM properties_normalized p
                     WHERE COALESCE(p.deal_closed, false) = true
                       AND p.updated_at >= :pms AND p.updated_at < :pme) AS d_prev,
                    (SELECT COUNT(*)::int
                     FROM properties_normalized p
                     INNER JOIN property_status ps ON ps.id = p.property_status_id
                     WHERE LOWER(TRIM(COALESCE(ps.slug, ''))) IN ('pending', 'draft')
                    ) AS pend_all,
                    (SELECT COUNT(*)::int
                     FROM properties_normalized p
                     INNER JOIN property_status ps ON ps.id = p.property_status_id
                     WHERE LOWER(TRIM(COALESCE(ps.slug, ''))) IN ('pending', 'draft')
                       AND (
                            (p.created_at >= :d0 AND p.created_at < :d1)
                         OR (p.updated_at >= :d0 AND p.updated_at < :d1)
                       )
                    ) AS pend_today
                """
            ),
            {
                "ms": month_start,
                "mee": next_start,
                "pms": prev_start,
                "pme": month_start,
                "registered_role": UserRoles.REGISTERED_USER,
                "agent_role": UserRoles.AGENT,
                "d0": today_start,
                "d1": tomorrow_start,
            },
        ).mappings().one()
        mlabel = f"{year:04d}-{month:02d}"
        return KpiRawSnapshot(
            month_label=mlabel,
            users_curr=int(row["u_curr"] or 0),
            users_prev=int(row["u_prev"] or 0),
            agents_curr=int(row["ag_curr"] or 0),
            agents_prev=int(row["ag_prev"] or 0),
            listings_curr=int(row["l_curr"] or 0),
            listings_prev=int(row["l_prev"] or 0),
            leads_curr=int(row["ld_curr"] or 0),
            leads_prev=int(row["ld_prev"] or 0),
            deals_curr=int(row["d_curr"] or 0),
            deals_prev=int(row["d_prev"] or 0),
            pending_approvals=int(row["pend_all"] or 0),
            pending_approvals_today=int(row["pend_today"] or 0),
        )

    def fetch_trends(
        self,
        *,
        num_months: int,
        end_year: int,
        end_month: int,
    ) -> TrendsRaw:
        """
        Trailing N full calendar months ending at (end_year, end_month) inclusive.
        Series: new signups, new listings, and new leads per month (not cumulative).
        monthLabels: oldest to newest, English 3-letter abbrev.
        """
        if not 1 <= num_months <= 24:
            raise ValueError("months must be between 1 and 24")
        if not 1 <= end_month <= 12 or not 2000 <= end_year <= 2100:
            raise ValueError("Invalid end month")
        fy, fm = _shift_calendar_month(end_year, end_month, -(num_months - 1))
        first_ms = _month_start_utc(fy, fm)
        last_ms = _month_start_utc(end_year, end_month)

        query = self._db.execute(
            text(
                """
                SELECT
                    s.bucket_start,
                    (SELECT COUNT(DISTINCT u.id)::int
                     FROM users u
                     INNER JOIN user_roles ur ON ur.user_id = u.id
                     INNER JOIN roles r ON r.id = ur.role_id AND r.name = :registered_role
                     WHERE u.created_at >= s.bucket_start
                       AND u.created_at < s.bucket_start + interval '1 month'
                       AND u.deleted_at IS NULL) AS u_cnt,
                    (SELECT COUNT(*)::int FROM properties_normalized p
                     WHERE p.created_at >= s.bucket_start
                       AND p.created_at < s.bucket_start + interval '1 month') AS l_cnt,
                    (SELECT COUNT(l.id)::int FROM leads l
                     WHERE l.created_at >= s.bucket_start
                       AND l.created_at < s.bucket_start + interval '1 month') AS ld_cnt
                FROM (
                    SELECT generate_series(
                        :first_ms,
                        :last_ms,
                        interval '1 month'
                    ) AS bucket_start
                ) s
                ORDER BY s.bucket_start
                """
            ),
            {
                "first_ms": first_ms,
                "last_ms": last_ms,
                "registered_role": UserRoles.REGISTERED_USER,
            },
        )
        month_labels: List[str] = []
        user_s: List[int] = []
        list_s: List[int] = []
        lead_s: List[int] = []
        for gr in query.mappings().all():
            bs = gr["bucket_start"]
            if bs is not None and hasattr(bs, "month"):
                mnum = int(bs.month)
            else:
                mnum = 1
            month_labels.append(calendar.month_abbr[mnum])
            user_s.append(int(gr["u_cnt"] or 0))
            list_s.append(int(gr["l_cnt"] or 0))
            lead_s.append(int(gr["ld_cnt"] or 0))

        return TrendsRaw(
            month_labels=month_labels,
            user_growth_series=user_s,
            listing_growth_series=list_s,
            lead_growth_series=lead_s,
            months=num_months,
        )

    def fetch_rolling_cumulative_12m_utc(self) -> TrendsRaw:
        """Cumulative registered users / listings / leads (counts strictly before each month end); legacy /dashboard/summary charts."""
        growth_rows = self._db.execute(
            text(
                """
                WITH bounds AS (
                    SELECT generate_series(
                        date_trunc('month', (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')) - INTERVAL '11 months',
                        date_trunc('month', (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')),
                        INTERVAL '1 month'
                    ) AS month_start
                ),
                months AS (
                    SELECT
                        month_start,
                        (month_start + INTERVAL '1 month') AS month_end_exclusive
                    FROM bounds
                )
                SELECT
                    m.month_start,
                    (SELECT COUNT(DISTINCT u.id)::int
                     FROM users u
                     INNER JOIN user_roles ur ON ur.user_id = u.id
                     INNER JOIN roles r ON r.id = ur.role_id AND r.name = :registered_role
                     WHERE u.created_at < m.month_end_exclusive
                       AND u.deleted_at IS NULL) AS cum_users,
                    (SELECT COUNT(*)::int FROM properties_normalized p
                     WHERE p.created_at < m.month_end_exclusive) AS cum_listings,
                    (SELECT COUNT(*)::int FROM leads l
                     WHERE l.created_at < m.month_end_exclusive) AS cum_leads
                FROM months m
                ORDER BY m.month_start ASC
                """
            ),
            {"registered_role": UserRoles.REGISTERED_USER},
        ).mappings().all()
        month_labels: List[str] = []
        user_s: List[int] = []
        list_s: List[int] = []
        lead_s: List[int] = []
        for gr in growth_rows:
            ms = gr["month_start"]
            mnum = int(ms.month) if hasattr(ms, "month") else 1
            month_labels.append(calendar.month_abbr[mnum])
            user_s.append(int(gr["cum_users"] or 0))
            list_s.append(int(gr["cum_listings"] or 0))
            lead_s.append(int(gr["cum_leads"] or 0))
        return TrendsRaw(
            month_labels=month_labels,
            user_growth_series=user_s,
            listing_growth_series=list_s,
            lead_growth_series=lead_s,
            months=12,
        )

    def fetch_lead_source_breakdown(self) -> tuple[list[str], list[int]]:
        lead_rows = self._db.execute(
            text(
                """
                SELECT
                    COALESCE(NULLIF(TRIM(l.inquiry_type), ''), 'Unspecified') AS label,
                    COUNT(l.id)::int AS cnt
                FROM leads l
                GROUP BY 1
                ORDER BY cnt DESC
                LIMIT 10
                """
            )
        ).mappings().all()
        return [str(r["label"]) for r in lead_rows], [int(r["cnt"] or 0) for r in lead_rows]

    def fetch_recent_activity_for_user(self, *, user_id: UUID, limit: int = 5) -> list[ActivityLogItem]:
        """Fetch latest activity log items for a specific user.

        Mirrors agent dashboard semantics:
        - Ordered newest-first by `COALESCE(updated_at, created_at)`
        - Uses `activity_logs.message` and `activity_logs.tone` (default tone = 'info')
        """
        lim = max(0, min(int(limit or 0), 50))
        if lim <= 0:
            return []
        rows = (
            self._db.execute(
                text(
                    """
                    SELECT
                        al.message,
                        COALESCE(al.tone, 'info') AS tone,
                        COALESCE(al.updated_at, al.created_at) AS activity_at
                    FROM activity_logs al
                    WHERE al.user_id = :uid
                    ORDER BY COALESCE(al.updated_at, al.created_at) DESC
                    LIMIT :lim
                    """
                ),
                {"uid": user_id, "lim": lim},
            )
            .mappings()
            .all()
        )
        return [
            ActivityLogItem(
                text=str(r["message"] or ""),
                tone=str(r["tone"] or "info"),
                activity_at=r["activity_at"],
            )
            for r in rows
        ]

    def count_active_assigned_agents_for_admin(self, *, admin_id: UUID) -> int:
        """Count distinct agents actively linked to the given admin.

        "Active" assignment semantics match `AgentAssignmentStatus.ACTIVE`:
        `is_active = true` and `revoked_at IS NULL`. Deleted users are excluded
        (`users.deleted_at IS NULL`); `users.is_active` is NOT considered.
        """
        row = (
            self._db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT aaa.agent_id)::int AS cnt
                    FROM admin_agent_assignments aaa
                    INNER JOIN users u ON u.id = aaa.agent_id
                    WHERE aaa.admin_id = :admin_id
                      AND aaa.is_active = true
                      AND aaa.revoked_at IS NULL
                      AND u.deleted_at IS NULL
                    """
                ),
                {"admin_id": admin_id},
            )
            .mappings()
            .one()
        )
        return int(row["cnt"] or 0)

    def fetch_inherited_admin_ids_for_agent(self, *, agent_id: UUID) -> list[UUID]:
        """Admins whose roles/permissions are inherited by this agent.

        Mirrors RBAC inheritance constraints:
        `is_active = true`, `revoked_at IS NULL`, `can_inherit_privileges = true`.
        Deleted admins are excluded (`users.deleted_at IS NULL`); `users.is_active`
        is not considered here because authentication already enforces it.
        """
        rows = (
            self._db.execute(
                text(
                    """
                    SELECT DISTINCT aaa.admin_id
                    FROM admin_agent_assignments aaa
                    INNER JOIN users u ON u.id = aaa.admin_id
                    WHERE aaa.agent_id = :agent_id
                      AND aaa.is_active = true
                      AND aaa.revoked_at IS NULL
                      AND aaa.can_inherit_privileges = true
                      AND u.deleted_at IS NULL
                    ORDER BY aaa.admin_id
                    """
                ),
                {"agent_id": agent_id},
            )
            .mappings()
            .all()
        )
        return [r["admin_id"] for r in rows if r.get("admin_id") is not None]

    def fetch_total_user_counts_by_role(self) -> dict:
        """Platform-wide counts by role (admin/registered_user), excluding deleted users only."""
        row = (
            self._db.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(DISTINCT ur.user_id)::int
                         FROM user_roles ur
                         INNER JOIN roles r ON r.id = ur.role_id AND r.name = :registered_role
                         INNER JOIN users u ON u.id = ur.user_id AND u.deleted_at IS NULL
                        ) AS registered_users,
                        (SELECT COUNT(DISTINCT ur.user_id)::int
                         FROM user_roles ur
                         INNER JOIN roles r ON r.id = ur.role_id AND r.name = :admin_role
                         INNER JOIN users u ON u.id = ur.user_id AND u.deleted_at IS NULL
                        ) AS admins
                    """
                ),
                {
                    "registered_role": UserRoles.REGISTERED_USER,
                    "admin_role": UserRoles.ADMIN,
                },
            )
            .mappings()
            .one()
        )
        return {
            "totalRegisterUserCount": int(row["registered_users"] or 0),
            "totalAdminCount": int(row["admins"] or 0),
        }

    def fetch_top_properties_by_views(
        self,
        *,
        period: str,
        page: int = 1,
        limit: int = 5,
        agent_id: Optional[UUID] = None,
    ) -> tuple[list[PropertyPerformanceRow], int]:
        """Top properties by view count (time window from ``period``), optional agent filter, paginated.

        Returns:
            (rows for the requested page, total distinct properties matching filters).
        """
        time_sql = _property_performance_time_filter_sql(period)
        lim = max(1, min(limit, 100))
        pg = max(1, page)
        offset = (pg - 1) * lim
        where_agent = ""
        count_params: dict = {}
        data_params: dict = {"lim": lim, "off": offset}
        if agent_id is not None:
            where_agent = " AND p.agent_user_id = :aid"
            count_params["aid"] = agent_id
            data_params["aid"] = agent_id

        base_from = """
                FROM property_views pv
                INNER JOIN properties_normalized p ON p.id = pv.property_id
                LEFT JOIN users u ON u.id = p.agent_user_id
                LEFT JOIN property_categories pc ON pc.id = p.category_id
                LEFT JOIN property_types pt ON pt.id = p.type_id
                LEFT JOIN areas a ON a.id = p.location_id
                WHERE 1=1
        """
        count_sql = f"""
                SELECT COUNT(*)::int AS cnt FROM (
                    SELECT p.id
                    {base_from}
                    {time_sql}{where_agent}
                    GROUP BY p.id
                ) property_groups
        """
        total = int(self._db.execute(text(count_sql), count_params).scalar() or 0)

        data_sql = f"""
                SELECT
                    p.id AS property_id,
                    p.agent_user_id AS agent_user_id,
                    COALESCE(u.full_name, 'Unassigned') AS agent_name,
                    pc.name AS category_name,
                    pt.name AS type_name,
                    LOWER(NULLIF(TRIM(COALESCE(pt.slug, '')), '')) AS type_slug,
                    COALESCE(NULLIF(TRIM(a.name), ''), NULLIF(TRIM(p.location_name), ''), '') AS area_or_location,
                    p.title AS title,
                    COUNT(pv.id)::int AS view_count
                {base_from}
                    {time_sql}{where_agent}
                GROUP BY p.id, p.agent_user_id, u.full_name, pc.name, pt.name, pt.slug, a.name, p.location_name, p.title
                ORDER BY view_count DESC, p.id ASC
                LIMIT :lim OFFSET :off
        """
        perf_rows = self._db.execute(text(data_sql), data_params).mappings().all()
        rows = [
            PropertyPerformanceRow(
                property_id=r["property_id"],
                agent_user_id=r["agent_user_id"],
                agent_name=(r["agent_name"] or "Unassigned")
                if r["agent_name"] is not None
                else "Unassigned",
                category_name=r["category_name"],
                type_name=r["type_name"],
                type_slug=r["type_slug"] if r["type_slug"] else None,
                area_or_location=r["area_or_location"] or "",
                title=r["title"],
                view_count=int(r["view_count"] or 0),
            )
            for r in perf_rows
        ]
        return rows, total
