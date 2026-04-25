"""Service layer for agent/admin dashboard summary."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

from fastapi import HTTPException

from app.models.user import User
from app.repositories.agent_dashboard_repository import AgentDashboardRepository
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.status_codes import HTTPStatus


class AgentDashboardService:
    """Build dashboard response payload for current authenticated user."""

    def __init__(self, repo: AgentDashboardRepository) -> None:
        self._repo = repo

    @staticmethod
    def _relative_time(activity_at: datetime) -> str:
        """Return UI-friendly relative time string."""
        now = datetime.now(timezone.utc)
        dt = activity_at if activity_at.tzinfo else activity_at.replace(tzinfo=timezone.utc)
        delta = max((now - dt).total_seconds(), 0)

        if delta < 60:
            return "just now"
        if delta < 3600:
            minutes = int(delta // 60)
            return f"{minutes} min ago"
        if delta < 86400:
            hours = int(delta // 3600)
            return f"{hours} hr ago"
        days = int(delta // 86400)
        return f"{days} day ago" if days == 1 else f"{days} days ago"

    @staticmethod
    def _has_agent_role(user: User) -> bool:
        return UserRoles.AGENT in {role.name for role in user.roles}

    @staticmethod
    def _mom_percent_change(current: int, previous: int) -> float:
        """Aligned month-to-date percent change; edge cases per product rules."""
        if previous == 0:
            return 0.0 if current == 0 else 100.0
        raw = ((current - previous) / previous) * 100
        return float(Decimal(str(raw)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    def get_dashboard_summary(self, current_user: User) -> Dict:
        """Return dashboard summary for the agent's own scope (routed: agent role only)."""
        if not self._has_agent_role(current_user):
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.MISSING_ROLE.format(role=UserRoles.AGENT),
            )
        agent_ids = [current_user.id]
        metrics = self._repo.get_metrics(agent_ids=agent_ids)

        conversion_rate = Decimal("0")
        if metrics.leads_this_month > 0:
            conversion_rate = (
                Decimal(metrics.deal_close_count) * Decimal("100") / Decimal(metrics.leads_this_month)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        return {
            "totalProperties": metrics.total_properties,
            "leadsThisMonth": metrics.leads_this_month,
            "dealCloseCount": metrics.deal_close_count,
            "conversionRate": int(conversion_rate),
            "totalPropertyViews": metrics.total_property_views,
            "activeProperties": metrics.active_properties,
            "draftProperties": metrics.draft_properties,
            "inquiryVolumeAllTime": metrics.inquiry_volume_all_time,
            "inquiryVolumeLast7Days": metrics.inquiry_volume_last_7_days,
            "inquiryTrendLast30Days": metrics.inquiry_trend_last_30_days,
            "listingsChangePercent": self._mom_percent_change(
                metrics.listings_mtd_current,
                metrics.listings_mtd_previous,
            ),
            "leadsChangePercent": self._mom_percent_change(
                metrics.leads_mtd_current,
                metrics.leads_mtd_previous,
            ),
            "dealsClosedChangePercent": self._mom_percent_change(
                metrics.deals_mtd_current,
                metrics.deals_mtd_previous,
            ),
            "propertyViewsChangePercent": self._mom_percent_change(
                metrics.views_mtd_current,
                metrics.views_mtd_previous,
            ),
            "recentActivity": [
                {
                    "text": item.text,
                    "time": self._relative_time(item.activity_at),
                    "tone": item.tone,
                }
                for item in metrics.recent_activity
            ],
        }

