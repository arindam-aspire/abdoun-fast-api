"""Repository for agent/admin dashboard summary metrics."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import AdminAgentAssignment


@dataclass
class ActivityLogItem:
    text: str
    tone: str
    activity_at: datetime


@dataclass
class DashboardSummaryMetrics:
    total_properties: int
    active_properties: int
    draft_properties: int
    leads_this_month: int
    deal_close_count: int
    inquiry_volume_all_time: int
    inquiry_volume_last_7_days: int
    total_property_views: int
    inquiry_trend_last_30_days: List[int]
    recent_activity: List[ActivityLogItem]
    listings_mtd_current: int
    listings_mtd_previous: int
    leads_mtd_current: int
    leads_mtd_previous: int
    deals_mtd_current: int
    deals_mtd_previous: int
    views_mtd_current: int
    views_mtd_previous: int


def _dashboard_summary_from_parts(
    property_counts: dict,
    inquiry_counts: dict,
    total_property_views: int,
    trend_values: List[int],
    activity: List[ActivityLogItem],
    mtd_row: dict,
) -> DashboardSummaryMetrics:
    return DashboardSummaryMetrics(
        total_properties=property_counts["total_properties"] or 0,
        active_properties=property_counts["active_properties"] or 0,
        draft_properties=property_counts["draft_properties"] or 0,
        leads_this_month=inquiry_counts["leads_this_month"] or 0,
        deal_close_count=property_counts["deal_close_count"] or 0,
        inquiry_volume_all_time=inquiry_counts["inquiry_volume_all_time"] or 0,
        inquiry_volume_last_7_days=inquiry_counts["inquiry_volume_last_7_days"] or 0,
        total_property_views=total_property_views,
        inquiry_trend_last_30_days=trend_values,
        recent_activity=activity,
        listings_mtd_current=mtd_row["listings_curr"] or 0,
        listings_mtd_previous=mtd_row["listings_prev"] or 0,
        leads_mtd_current=mtd_row["leads_curr"] or 0,
        leads_mtd_previous=mtd_row["leads_prev"] or 0,
        deals_mtd_current=mtd_row["deals_curr"] or 0,
        deals_mtd_previous=mtd_row["deals_prev"] or 0,
        views_mtd_current=mtd_row["views_curr"] or 0,
        views_mtd_previous=mtd_row["views_prev"] or 0,
    )


def _empty_dashboard_metrics() -> DashboardSummaryMetrics:
    """Zeroed metrics including MTD slots for MoM deltas."""
    return DashboardSummaryMetrics(
        total_properties=0,
        active_properties=0,
        draft_properties=0,
        leads_this_month=0,
        deal_close_count=0,
        inquiry_volume_all_time=0,
        inquiry_volume_last_7_days=0,
        total_property_views=0,
        inquiry_trend_last_30_days=[0] * 30,
        recent_activity=[],
        listings_mtd_current=0,
        listings_mtd_previous=0,
        leads_mtd_current=0,
        leads_mtd_previous=0,
        deals_mtd_current=0,
        deals_mtd_previous=0,
        views_mtd_current=0,
        views_mtd_previous=0,
    )


def _aligned_mtd_bounds(now_utc: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """Current MTD vs same elapsed time in previous month (UTC)."""
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        prev_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_start = month_start.replace(month=month_start.month - 1)
    prev_end = prev_start + (now_utc - month_start)
    return month_start, now_utc, prev_start, prev_end


class AgentDashboardRepository:
    """Read-only analytics queries for dashboard summary."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_effective_agent_ids(self, current_user_id: uuid.UUID, *, is_admin: bool) -> List[uuid.UUID]:
        """Return scoped agent ids: self for agent, assigned agents for admin."""
        if not is_admin:
            return [current_user_id]
        rows = (
            self._db.query(AdminAgentAssignment.agent_id)
            .filter(
                AdminAgentAssignment.admin_id == current_user_id,
                AdminAgentAssignment.is_active.is_(True),
            )
            .all()
        )
        return [row[0] for row in rows]

    def _inquiry_trend_last_30_days(self, params: dict) -> List[int]:
        trend_rows = self._db.execute(
            text(
                """
                SELECT
                    DATE(l.created_at AT TIME ZONE 'UTC') AS day,
                    COUNT(l.id)::int AS count
                FROM leads l
                JOIN properties_normalized p ON p.id = l.property_id
                WHERE p.agent_user_id = ANY(:agent_ids)
                  AND l.created_at >= date_trunc('day', (NOW() AT TIME ZONE 'UTC') - INTERVAL '29 days')
                GROUP BY DATE(l.created_at AT TIME ZONE 'UTC')
                ORDER BY day ASC
                """
            ),
            params,
        ).mappings().all()
        trend_by_day = {row["day"]: row["count"] for row in trend_rows}
        today_utc = datetime.now(timezone.utc).date()
        return [int(trend_by_day.get(today_utc - timedelta(days=idx), 0)) for idx in range(29, -1, -1)]

    def _fetch_recent_activity(self, params: dict, activity_limit: int) -> List[ActivityLogItem]:
        activity_rows = self._db.execute(
            text(
                """
                SELECT
                    al.message,
                    COALESCE(al.tone, 'info') AS tone,
                    COALESCE(al.updated_at, al.created_at) AS activity_at
                FROM activity_logs al
                WHERE al.user_id = ANY(:agent_ids)
                ORDER BY COALESCE(al.updated_at, al.created_at) DESC
                LIMIT :activity_limit
                """
            ),
            {**params, "activity_limit": activity_limit},
        ).mappings().all()
        return [
            ActivityLogItem(
                text=row["message"] or "",
                tone=row["tone"] or "info",
                activity_at=row["activity_at"],
            )
            for row in activity_rows
        ]

    def _fetch_core_counts(self, params: dict) -> tuple[dict, dict, int]:
        property_counts = self._db.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS total_properties,
                    COUNT(*) FILTER (WHERE COALESCE(ps.slug, '') = 'active')::int AS active_properties,
                    COUNT(*) FILTER (WHERE COALESCE(ps.slug, '') = 'draft')::int AS draft_properties,
                    COUNT(*) FILTER (WHERE COALESCE(p.deal_closed, false) = true)::int AS deal_close_count
                FROM properties_normalized p
                LEFT JOIN property_status ps ON ps.id = p.property_status_id
                WHERE p.agent_user_id = ANY(:agent_ids)
                """
            ),
            params,
        ).mappings().one()

        inquiry_counts = self._db.execute(
            text(
                """
                SELECT
                    COUNT(l.id)::int AS inquiry_volume_all_time,
                    COUNT(l.id) FILTER (
                        WHERE l.created_at >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '7 days'
                    )::int AS inquiry_volume_last_7_days,
                    COUNT(l.id) FILTER (
                        WHERE l.created_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC')
                          AND l.created_at <= NOW() AT TIME ZONE 'UTC'
                    )::int AS leads_this_month
                FROM leads l
                JOIN properties_normalized p ON p.id = l.property_id
                WHERE p.agent_user_id = ANY(:agent_ids)
                """
            ),
            params,
        ).mappings().one()

        total_property_views = self._db.execute(
            text(
                """
                SELECT COUNT(pv.id)::int AS total_property_views
                FROM property_views pv
                JOIN properties_normalized p ON p.id = pv.property_id
                WHERE p.agent_user_id = ANY(:agent_ids)
                """
            ),
            params,
        ).scalar_one() or 0

        return property_counts, inquiry_counts, int(total_property_views)

    def _fetch_mtd_comparison(self, params: dict) -> dict:
        now_utc = datetime.now(timezone.utc)
        cs, ce, ps, pe = _aligned_mtd_bounds(now_utc)
        mtd_params = {**params, "cs": cs, "ce": ce, "ps": ps, "pe": pe}
        return self._db.execute(
            text(
                """
                SELECT
                    (
                        SELECT COUNT(*)::int
                        FROM properties_normalized p
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND p.created_at >= :cs AND p.created_at <= :ce
                    ) AS listings_curr,
                    (
                        SELECT COUNT(*)::int
                        FROM properties_normalized p
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND p.created_at >= :ps AND p.created_at <= :pe
                    ) AS listings_prev,
                    (
                        SELECT COUNT(l.id)::int
                        FROM leads l
                        JOIN properties_normalized p ON p.id = l.property_id
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND l.created_at >= :cs AND l.created_at <= :ce
                    ) AS leads_curr,
                    (
                        SELECT COUNT(l.id)::int
                        FROM leads l
                        JOIN properties_normalized p ON p.id = l.property_id
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND l.created_at >= :ps AND l.created_at <= :pe
                    ) AS leads_prev,
                    (
                        SELECT COUNT(*)::int
                        FROM properties_normalized p
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND COALESCE(p.deal_closed, false) = true
                          AND p.updated_at >= :cs AND p.updated_at <= :ce
                    ) AS deals_curr,
                    (
                        SELECT COUNT(*)::int
                        FROM properties_normalized p
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND COALESCE(p.deal_closed, false) = true
                          AND p.updated_at >= :ps AND p.updated_at <= :pe
                    ) AS deals_prev,
                    (
                        SELECT COUNT(pv.id)::int
                        FROM property_views pv
                        JOIN properties_normalized p ON p.id = pv.property_id
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND pv.viewed_at >= :cs AND pv.viewed_at <= :ce
                    ) AS views_curr,
                    (
                        SELECT COUNT(pv.id)::int
                        FROM property_views pv
                        JOIN properties_normalized p ON p.id = pv.property_id
                        WHERE p.agent_user_id = ANY(:agent_ids)
                          AND pv.viewed_at >= :ps AND pv.viewed_at <= :pe
                    ) AS views_prev
                """
            ),
            mtd_params,
        ).mappings().one()

    def get_metrics(self, agent_ids: List[uuid.UUID], *, activity_limit: int = 5) -> DashboardSummaryMetrics:
        """Compute all summary metrics for given agent ids.

        Recent activity is ordered newest-first; ``activity_limit`` caps how many rows are returned (default 5).
        """
        if not agent_ids:
            return _empty_dashboard_metrics()

        params = {"agent_ids": agent_ids}

        property_counts, inquiry_counts, total_property_views = self._fetch_core_counts(params)

        trend_values = self._inquiry_trend_last_30_days(params)
        activity = self._fetch_recent_activity(params, activity_limit)
        mtd_row = self._fetch_mtd_comparison(params)

        return _dashboard_summary_from_parts(
            property_counts,
            inquiry_counts,
            total_property_views,
            trend_values,
            activity,
            mtd_row,
        )

