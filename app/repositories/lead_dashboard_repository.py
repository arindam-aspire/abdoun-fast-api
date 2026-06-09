"""Repository for lead analytics dashboard metrics (scope- and range-aware).

All aggregation is pushed down to PostgreSQL (filtered counts, ``date_trunc``
buckets, lateral first-response lookup) so the service stays I/O light, mirroring
the existing ``agent_dashboard_repository`` / ``admin_dashboard_repository`` style.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.constants import LeadDashboardConstants


@dataclass
class LeadComplianceMetrics:
    """Raw, scope-filtered lead data-quality / SLA compliance metrics (all-time)."""

    total_leads: int = 0
    sla_breach_count: int = 0
    avg_response_hours: float = 0.0
    active_total: int = 0
    follow_up_compliant: int = 0
    missing_source_count: int = 0
    duplicate_count: int = 0
    missing_lost_reason_count: int = 0


@dataclass
class LeadDashboardMetrics:
    """Raw, scope-filtered metrics for a single range window."""

    total_leads: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    avg_aging_days: float = 0.0
    avg_response_hours: float = 0.0
    sla_breach_count: int = 0
    source_performance: list[dict] = field(default_factory=list)
    aging_buckets: dict[str, int] = field(default_factory=dict)
    trend: list[dict] = field(default_factory=list)


# range -> (window start offset, date_trunc unit, number of trend buckets)
_RANGE_TREND_CONFIG: dict[str, tuple[timedelta, str, int]] = {
    LeadDashboardConstants.RANGE_DAY: (timedelta(days=1), "hour", 24),
    LeadDashboardConstants.RANGE_WEEK: (timedelta(days=7), "day", 7),
    LeadDashboardConstants.RANGE_MONTH: (timedelta(days=30), "day", 30),
    LeadDashboardConstants.RANGE_QUARTER: (timedelta(weeks=13), "week", 13),
    LeadDashboardConstants.RANGE_YEAR: (timedelta(days=365), "month", 12),
}


def _range_start(range_key: str, now_utc: datetime) -> datetime:
    offset, _unit, _count = _RANGE_TREND_CONFIG[range_key]
    return now_utc - offset


def _trend_unit(range_key: str) -> str:
    return _RANGE_TREND_CONFIG[range_key][1]


def _bucket_label(dt: datetime, unit: str) -> str:
    if unit == "hour":
        return dt.strftime("%Y-%m-%d %H:00")
    if unit == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


def _expected_buckets(range_key: str, now_utc: datetime) -> list[str]:
    """Chronological, gap-free bucket labels covering the whole window."""
    _offset, unit, count = _RANGE_TREND_CONFIG[range_key]
    if unit == "hour":
        anchor = now_utc.replace(minute=0, second=0, microsecond=0)
        starts = [anchor - timedelta(hours=i) for i in range(count - 1, -1, -1)]
    elif unit == "day":
        anchor = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        starts = [anchor - timedelta(days=i) for i in range(count - 1, -1, -1)]
    elif unit == "week":
        anchor = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        anchor = anchor - timedelta(days=anchor.weekday())  # ISO week start (Monday)
        starts = [anchor - timedelta(weeks=i) for i in range(count - 1, -1, -1)]
    else:  # month
        anchor = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        starts = []
        year, month = anchor.year, anchor.month
        for i in range(count - 1, -1, -1):
            total = (year * 12 + (month - 1)) - i
            starts.append(anchor.replace(year=total // 12, month=(total % 12) + 1))
    return [_bucket_label(dt, unit) for dt in starts]


class LeadDashboardRepository:
    """Read-only analytics queries for the lead dashboard summary."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _scope_clause(self, *, scope: str) -> str:
        """Return an SQL fragment scoping leads to the caller (admin = all)."""
        if scope == "agent":
            return "AND l.assigned_agent_id = :actor_id"
        return ""

    def get_metrics(
        self,
        *,
        scope: str,
        range_key: str,
        actor_id: Optional[uuid.UUID] = None,
    ) -> LeadDashboardMetrics:
        now_utc = datetime.now(timezone.utc)
        start_at = _range_start(range_key, now_utc)
        scope_sql = self._scope_clause(scope=scope)
        params: dict = {"start_at": start_at}
        if scope == "agent":
            params["actor_id"] = actor_id

        status_counts, total = self._fetch_status_counts(params, scope_sql)
        avg_aging_days, avg_response_hours, sla_breach = self._fetch_aging_and_sla(params, scope_sql)
        source_performance = self._fetch_source_performance(params, scope_sql)
        aging_buckets = self._fetch_aging_buckets(params, scope_sql)
        trend = self._fetch_trend(params, scope_sql, range_key=range_key, now_utc=now_utc)

        return LeadDashboardMetrics(
            total_leads=total,
            status_counts=status_counts,
            avg_aging_days=avg_aging_days,
            avg_response_hours=avg_response_hours,
            sla_breach_count=sla_breach,
            source_performance=source_performance,
            aging_buckets=aging_buckets,
            trend=trend,
        )

    def get_compliance_metrics(
        self,
        *,
        scope: str,
        actor_id: Optional[uuid.UUID] = None,
    ) -> LeadComplianceMetrics:
        """All-time lead compliance/data-quality metrics for the caller's scope."""
        scope_sql = self._scope_clause(scope=scope)
        params: dict = {}
        if scope == "agent":
            params["actor_id"] = actor_id

        core = self._fetch_compliance_core(params, scope_sql)
        duplicate_count = self._fetch_duplicate_count(params, scope_sql)
        missing_lost_reason = self._fetch_missing_lost_reason_count(params, scope_sql)

        return LeadComplianceMetrics(
            total_leads=int(core["total_leads"] or 0),
            sla_breach_count=int(core["sla_breach_count"] or 0),
            avg_response_hours=float(core["avg_response_hours"] or 0.0),
            active_total=int(core["active_total"] or 0),
            follow_up_compliant=int(core["follow_up_compliant"] or 0),
            missing_source_count=int(core["missing_source_count"] or 0),
            duplicate_count=duplicate_count,
            missing_lost_reason_count=missing_lost_reason,
        )

    def _fetch_compliance_core(self, params: dict, scope_sql: str) -> dict:
        return self._db.execute(
            text(
                f"""
                WITH base AS (
                    SELECT
                        l.status AS status,
                        l.source AS source,
                        l.created_at AS created_at,
                        l.last_activity_at AS last_activity_at,
                        (
                            SELECT MIN(m.created_at)
                            FROM lead_messages m
                            WHERE m.lead_id = l.id
                              AND (l.user_id IS NULL OR m.sender_user_id IS DISTINCT FROM l.user_id)
                        ) AS first_response_at
                    FROM leads l
                    WHERE 1 = 1
                    {scope_sql}
                )
                SELECT
                    COUNT(*)::int AS total_leads,
                    COUNT(*) FILTER (
                        WHERE (
                            first_response_at IS NOT NULL
                            AND first_response_at - created_at > make_interval(hours => :sla_hours)
                        ) OR (
                            first_response_at IS NULL
                            AND status <> 'CLOSED'
                            AND NOW() - created_at > make_interval(hours => :sla_hours)
                        )
                    )::int AS sla_breach_count,
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (first_response_at - created_at)) / 3600.0)
                            FILTER (WHERE first_response_at IS NOT NULL),
                        0
                    )::float AS avg_response_hours,
                    COUNT(*) FILTER (WHERE status <> 'CLOSED')::int AS active_total,
                    COUNT(*) FILTER (
                        WHERE status <> 'CLOSED'
                          AND last_activity_at IS NOT NULL
                          AND last_activity_at >= NOW() - make_interval(hours => :followup_hours)
                    )::int AS follow_up_compliant,
                    COUNT(*) FILTER (
                        WHERE source IS NULL OR TRIM(source::text) = ''
                    )::int AS missing_source_count
                FROM base
                """
            ),
            {
                **params,
                "sla_hours": LeadDashboardConstants.SLA_FIRST_RESPONSE_HOURS,
                "followup_hours": LeadDashboardConstants.FOLLOW_UP_CADENCE_HOURS,
            },
        ).mappings().one()

    def _fetch_duplicate_count(self, params: dict, scope_sql: str) -> int:
        """Extra leads sharing the existing dedup signature (over active leads)."""
        value = self._db.execute(
            text(
                f"""
                WITH keyed AS (
                    SELECT
                        COALESCE(l.property_id::text, LOWER(TRIM(l.external_property_name))) AS prop_key,
                        COALESCE(
                            l.user_id::text,
                            regexp_replace(COALESCE(l.external_owner_phone, ''), '[^0-9+]', '', 'g')
                        ) AS contact_key
                    FROM leads l
                    WHERE l.status <> 'CLOSED'
                    {scope_sql}
                ),
                grp AS (
                    SELECT COUNT(*) AS c
                    FROM keyed
                    WHERE NULLIF(prop_key, '') IS NOT NULL
                      AND NULLIF(contact_key, '') IS NOT NULL
                    GROUP BY prop_key, contact_key
                    HAVING COUNT(*) > 1
                )
                SELECT COALESCE(SUM(c - 1), 0)::int AS duplicate_count
                FROM grp
                """
            ),
            params,
        ).scalar_one()
        return int(value or 0)

    def _fetch_missing_lost_reason_count(self, params: dict, scope_sql: str) -> int:
        """CLOSED leads with no recorded reason on their CLOSED transition."""
        value = self._db.execute(
            text(
                f"""
                SELECT COUNT(*)::int AS missing_lost_reason_count
                FROM leads l
                WHERE l.status = 'CLOSED'
                {scope_sql}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM lead_status_history h
                      WHERE h.lead_id = l.id
                        AND h.to_status = 'CLOSED'
                        AND COALESCE(TRIM(h.reason), '') <> ''
                  )
                """
            ),
            params,
        ).scalar_one()
        return int(value or 0)

    def _fetch_status_counts(self, params: dict, scope_sql: str) -> tuple[dict[str, int], int]:
        row = self._db.execute(
            text(
                f"""
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE l.status = 'NEW')::int AS new,
                    COUNT(*) FILTER (WHERE l.status = 'IN_PROGRESS')::int AS in_progress,
                    COUNT(*) FILTER (WHERE l.status = 'REQUEST_FOR_CLOSE')::int AS request_for_close,
                    COUNT(*) FILTER (WHERE l.status = 'CLOSED')::int AS closed
                FROM leads l
                WHERE l.created_at >= :start_at
                {scope_sql}
                """
            ),
            params,
        ).mappings().one()
        counts = {
            LeadDashboardConstants.STATUS_NEW: int(row["new"] or 0),
            LeadDashboardConstants.STATUS_IN_PROGRESS: int(row["in_progress"] or 0),
            LeadDashboardConstants.STATUS_REQUEST_FOR_CLOSE: int(row["request_for_close"] or 0),
            LeadDashboardConstants.STATUS_CLOSED: int(row["closed"] or 0),
        }
        return counts, int(row["total"] or 0)

    def _fetch_aging_and_sla(self, params: dict, scope_sql: str) -> tuple[float, float, int]:
        row = self._db.execute(
            text(
                f"""
                WITH base AS (
                    SELECT
                        l.status AS status,
                        l.created_at AS created_at,
                        l.closed_at AS closed_at,
                        (
                            SELECT MIN(m.created_at)
                            FROM lead_messages m
                            WHERE m.lead_id = l.id
                              AND (l.user_id IS NULL OR m.sender_user_id IS DISTINCT FROM l.user_id)
                        ) AS first_response_at
                    FROM leads l
                    WHERE l.created_at >= :start_at
                    {scope_sql}
                )
                SELECT
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (COALESCE(closed_at, NOW()) - created_at)) / 86400.0),
                        0
                    )::float AS avg_aging_days,
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (first_response_at - created_at)) / 3600.0)
                            FILTER (WHERE first_response_at IS NOT NULL),
                        0
                    )::float AS avg_response_hours,
                    COUNT(*) FILTER (
                        WHERE (
                            first_response_at IS NOT NULL
                            AND first_response_at - created_at > make_interval(hours => :sla_hours)
                        ) OR (
                            first_response_at IS NULL
                            AND status <> 'CLOSED'
                            AND NOW() - created_at > make_interval(hours => :sla_hours)
                        )
                    )::int AS sla_breach_count
                FROM base
                """
            ),
            {**params, "sla_hours": LeadDashboardConstants.SLA_FIRST_RESPONSE_HOURS},
        ).mappings().one()
        return (
            float(row["avg_aging_days"] or 0.0),
            float(row["avg_response_hours"] or 0.0),
            int(row["sla_breach_count"] or 0),
        )

    def _fetch_source_performance(self, params: dict, scope_sql: str) -> list[dict]:
        rows = self._db.execute(
            text(
                f"""
                SELECT
                    l.source AS source,
                    COUNT(*)::int AS total_leads,
                    COUNT(*) FILTER (WHERE l.status = 'CLOSED')::int AS converted
                FROM leads l
                WHERE l.created_at >= :start_at
                {scope_sql}
                GROUP BY l.source
                ORDER BY total_leads DESC, l.source ASC
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "source": str(r["source"]),
                "total_leads": int(r["total_leads"] or 0),
                "converted": int(r["converted"] or 0),
            }
            for r in rows
        ]

    def _fetch_aging_buckets(self, params: dict, scope_sql: str) -> dict[str, int]:
        rows = self._db.execute(
            text(
                f"""
                SELECT
                    CASE
                        WHEN age_days <= 1 THEN '0-1 days'
                        WHEN age_days <= 3 THEN '2-3 days'
                        WHEN age_days <= 7 THEN '4-7 days'
                        WHEN age_days <= 14 THEN '8-14 days'
                        WHEN age_days <= 30 THEN '15-30 days'
                        ELSE '31+ days'
                    END AS bucket,
                    COUNT(*)::int AS count
                FROM (
                    SELECT FLOOR(EXTRACT(EPOCH FROM (NOW() - l.created_at)) / 86400.0)::int AS age_days
                    FROM leads l
                    WHERE l.created_at >= :start_at
                      AND l.status <> 'CLOSED'
                    {scope_sql}
                ) s
                GROUP BY bucket
                """
            ),
            params,
        ).mappings().all()
        return {str(r["bucket"]): int(r["count"] or 0) for r in rows}

    def _fetch_trend(
        self,
        params: dict,
        scope_sql: str,
        *,
        range_key: str,
        now_utc: datetime,
    ) -> list[dict]:
        unit = _trend_unit(range_key)
        rows = self._db.execute(
            text(
                f"""
                SELECT
                    date_trunc(:trunc, l.created_at AT TIME ZONE 'UTC') AS bucket,
                    COUNT(*)::int AS total_leads,
                    COUNT(*) FILTER (WHERE l.status = 'CLOSED')::int AS converted
                FROM leads l
                WHERE l.created_at >= :start_at
                {scope_sql}
                GROUP BY date_trunc(:trunc, l.created_at AT TIME ZONE 'UTC')
                ORDER BY bucket ASC
                """
            ),
            {**params, "trunc": unit},
        ).mappings().all()

        by_label: dict[str, dict] = {}
        for r in rows:
            bucket = r["bucket"]
            if bucket is None:
                continue
            label = _bucket_label(bucket, unit)
            by_label[label] = {
                "total_leads": int(r["total_leads"] or 0),
                "converted": int(r["converted"] or 0),
            }

        out: list[dict] = []
        for label in _expected_buckets(range_key, now_utc):
            payload = by_label.get(label, {"total_leads": 0, "converted": 0})
            out.append({"period": label, **payload})
        return out
