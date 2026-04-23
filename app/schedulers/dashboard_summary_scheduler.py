"""Daily scheduler that refreshes dashboard_summary metrics."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from app.core.config import Settings
from app.db.session import SessionLocal
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import service_logger

_METRICS_QUERY = text(
    """
    WITH agents AS (
        SELECT DISTINCT u.id AS user_id
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id
        WHERE LOWER(r.name) = 'agent'
          AND COALESCE(u.is_active, true) = true
    ),
    property_metrics AS (
        SELECT
            p.agent_user_id AS user_id,
            COUNT(*)::int AS total_properties,
            COUNT(*) FILTER (WHERE COALESCE(ps.slug, '') = 'draft')::int AS draft_properties,
            COUNT(*) FILTER (WHERE COALESCE(ps.slug, '') = 'active')::int AS active_properties,
            COUNT(*) FILTER (WHERE COALESCE(p.deal_closed, false) = true)::int AS total_deals
        FROM properties_normalized p
        LEFT JOIN property_status ps ON ps.id = p.property_status_id
        WHERE p.agent_user_id IS NOT NULL
        GROUP BY p.agent_user_id
    ),
    view_metrics AS (
        SELECT
            p.agent_user_id AS user_id,
            COUNT(pv.id)::int AS total_views
        FROM property_views pv
        JOIN properties_normalized p ON p.id = pv.property_id
        WHERE p.agent_user_id IS NOT NULL
        GROUP BY p.agent_user_id
    ),
    inquiry_metrics AS (
        SELECT
            p.agent_user_id AS user_id,
            COUNT(l.id)::int AS total_inquiries
        FROM leads l
        JOIN properties_normalized p ON p.id = l.property_id
        WHERE p.agent_user_id IS NOT NULL
        GROUP BY p.agent_user_id
    )
    SELECT
        a.user_id,
        COALESCE(pm.total_properties, 0) AS total_properties,
        COALESCE(pm.active_properties, 0) AS active_properties,
        COALESCE(pm.draft_properties, 0) AS draft_properties,
        COALESCE(vm.total_views, 0) AS total_views,
        COALESCE(im.total_inquiries, 0) AS total_inquiries,
        COALESCE(pm.total_deals, 0) AS total_deals
    FROM agents a
    LEFT JOIN property_metrics pm ON pm.user_id = a.user_id
    LEFT JOIN view_metrics vm ON vm.user_id = a.user_id
    LEFT JOIN inquiry_metrics im ON im.user_id = a.user_id
    """
)


def _seconds_until_next_run(schedule_time: str) -> float:
    now = datetime.now()
    try:
        hour_str, minute_str = schedule_time.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        service_logger.warning(
            format_log_message(
                LogMessages.DashboardSummaryScheduler.INVALID_SCHEDULE_TIME,
                schedule_time=schedule_time,
            )
        )
        hour, minute = 0, 10

    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run = next_run + timedelta(days=1)
    return (next_run - now).total_seconds()


def refresh_dashboard_summary() -> int:
    """Rebuild dashboard_summary rows from current DB metrics."""
    db = SessionLocal()
    try:
        rows = db.execute(_METRICS_QUERY).mappings().all()
        current_ts = datetime.now(timezone.utc)

        db.execute(text("DELETE FROM dashboard_summary"))
        inserted = 0

        if rows:
            insert_stmt = text(
                """
                INSERT INTO dashboard_summary (
                    id,
                    user_id,
                    total_properties,
                    active_properties,
                    draft_properties,
                    total_views,
                    total_inquiries,
                    total_deals,
                    conversion_rate,
                    last_updated
                ) VALUES (
                    :id,
                    :user_id,
                    :total_properties,
                    :active_properties,
                    :draft_properties,
                    :total_views,
                    :total_inquiries,
                    :total_deals,
                    :conversion_rate,
                    :last_updated
                )
                """
            )

            payload = []
            for row in rows:
                inquiries = row["total_inquiries"] or 0
                deals = row["total_deals"] or 0
                conversion_rate = Decimal("0")
                if inquiries > 0:
                    conversion_rate = (Decimal(deals) * Decimal("100")) / Decimal(inquiries)

                payload.append(
                    {
                        "id": uuid.uuid4(),
                        "user_id": row["user_id"],
                        "total_properties": row["total_properties"] or 0,
                        "active_properties": row["active_properties"] or 0,
                        "draft_properties": row["draft_properties"] or 0,
                        "total_views": row["total_views"] or 0,
                        "total_inquiries": inquiries,
                        "total_deals": deals,
                        "conversion_rate": conversion_rate,
                        "last_updated": current_ts,
                    }
                )
            db.execute(insert_stmt, payload)
            inserted = len(payload)

        db.commit()
        service_logger.info(
            format_log_message(
                LogMessages.DashboardSummaryScheduler.REFRESH_SUCCESS,
                rows=inserted,
            )
        )
        return inserted
    except Exception:
        db.rollback()
        service_logger.exception(LogMessages.DashboardSummaryScheduler.REFRESH_FAILED)
        raise
    finally:
        db.close()


async def run_dashboard_summary_scheduler(settings: Settings) -> None:
    """Run the dashboard summary refresh every day at configured time."""
    while True:
        wait_seconds = _seconds_until_next_run(settings.dashboard_summary_schedule_time)
        service_logger.info(
            format_log_message(
                LogMessages.DashboardSummaryScheduler.SCHEDULER_SLEEP,
                wait_seconds=wait_seconds,
                schedule_time=settings.dashboard_summary_schedule_time,
            )
        )
        await asyncio.sleep(wait_seconds)
        refresh_dashboard_summary()
