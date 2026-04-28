"""Platform admin dashboard: KPIs, trends, and top properties by views."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException

from app.repositories.admin_dashboard_repository import (
    KpiRawSnapshot,
    PropertyPerformanceRow,
    ActivityLogItem,
    AdminDashboardRepository,
)
from app.schemas.admin_dashboard import PropertyPerformancePeriod
from app.models.user import User
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.status_codes import HTTPStatus

_MONTH_YM = re.compile(r"^(?P<y>\d{4})-(?P<m>0[1-9]|1[0-2])$")


def _mom_percent_change(current: int, previous: int) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    raw = ((current - previous) / previous) * 100
    return float(Decimal(str(raw)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _parse_ym_or_400(ym: str) -> tuple[int, int]:
    s = (ym or "").strip()
    m = _MONTH_YM.match(s)
    if not m:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_ADMIN_DASHBOARD_MONTH,
        )
    y, mo = int(m.group("y")), int(m.group("m"))
    if not 2000 <= y <= 2100:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=ErrorMessages.INVALID_ADMIN_DASHBOARD_MONTH,
        )
    return y, mo


def _kpi_to_public_dict(k: KpiRawSnapshot) -> Dict[str, Any]:
    return {
        "month": k.month_label,
        "registerUsersThisMonth": k.users_curr,
        "registerUsersMoMDelta": _mom_percent_change(k.users_curr, k.users_prev),
        "agentsThisMonth": k.agents_curr,
        "agentsMoMDelta": _mom_percent_change(k.agents_curr, k.agents_prev),
        "pendingApprovals": k.pending_approvals,
        "pendingApprovalsToday": k.pending_approvals_today,
        "listingsThisMonth": k.listings_curr,
        "listingsMoMDelta": _mom_percent_change(k.listings_curr, k.listings_prev),
        "leadsThisMonth": k.leads_curr,
        "leadsMoMDelta": _mom_percent_change(k.leads_curr, k.leads_prev),
        "closedDealsThisMonth": k.deals_curr,
    }


def _relative_time(activity_at: datetime) -> str:
    """Return UI-friendly relative time string (matches agent dashboard behavior)."""
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


def _activity_items_to_public(items: List[ActivityLogItem]) -> List[dict]:
    return [{"text": a.text, "time": _relative_time(a.activity_at), "tone": a.tone} for a in items]


def _build_property_items(rows: List[PropertyPerformanceRow]) -> List[dict]:
    out: List[dict] = []
    for row in rows:
        cat = (row.category_name or "").strip()
        typ = (row.type_name or "").strip()
        loc = (row.area_or_location or "").strip()
        bits = [b for b in (cat, typ, loc) if b]
        tail = ", ".join(bits) if bits else ((row.title or "").strip() or "Listing")
        title = (row.title or "").strip()
        out.append(
            {
                "label": f"{row.agent_name} - {tail}",
                "value": row.view_count,
                "propertyId": str(row.property_id),
                "agentId": str(row.agent_user_id) if row.agent_user_id else None,
                "agentName": row.agent_name,
                "propertyTitle": title or tail,
                "propertyType": row.type_slug or "",
            }
        )
    return out


class AdminDashboardService:
    """Admin dashboard: calendar-month KPIs, trailing trends, property performance."""

    def __init__(self, repo: AdminDashboardRepository) -> None:
        self._repo = repo

    @staticmethod
    def _has_direct_role(user: User, role_name: str) -> bool:
        # Keep "direct role" distinct from inherited RBAC roles.
        return role_name in {r.name for r in (user.roles or [])}

    def _resolve_effective_admin_id(self, current_user: User) -> UUID:
        """Resolve admin id for per-admin counts.

        - If the caller is a real admin user (direct `admin` role), use their user id.
        - If the caller is an agent inheriting admin role via assignment (RBAC feature),
          use the inherited admin id (first, stable order).
        - Fallback to caller id (keeps behavior deterministic even if data is inconsistent).
        """
        if self._has_direct_role(current_user, UserRoles.ADMIN):
            return current_user.id
        inherited = self._repo.fetch_inherited_admin_ids_for_agent(agent_id=current_user.id)
        return inherited[0] if inherited else current_user.id

    def get_kpis(self, month: str) -> Dict[str, Any]:
        y, m = _parse_ym_or_400(month)
        k = self._repo.fetch_kpis(year=y, month=m)
        return _kpi_to_public_dict(k)

    def get_trends(self, months: int, end_month: Optional[str]) -> Dict[str, Any]:
        if not 1 <= months <= 24:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_ADMIN_DASHBOARD_TRENDS_MONTHS,
            )
        if end_month is None or not str(end_month).strip():
            now_utc = datetime.now(timezone.utc)
            ey, em = now_utc.year, now_utc.month
        else:
            ey, em = _parse_ym_or_400(end_month)
        tr = self._repo.fetch_trends(num_months=months, end_year=ey, end_month=em)
        return {
            "months": tr.months,
            "monthLabels": tr.month_labels,
            "userGrowthSeries": tr.user_growth_series,
            "listingGrowthSeries": tr.listing_growth_series,
            "leadGrowthSeries": tr.lead_growth_series,
        }

    def get_property_performance(
        self,
        *,
        period: PropertyPerformancePeriod = PropertyPerformancePeriod.ALL,
        page: int = 1,
        limit: int = 5,
        agent_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(limit, 100))
        pg = max(1, page)
        rows, total = self._repo.fetch_top_properties_by_views(
            period=period.value,
            page=pg,
            limit=cap,
            agent_id=agent_id,
        )
        return {
            "items": _build_property_items(rows),
            "page": pg,
            "limit": cap,
            "totalItems": total,
        }

    def get_dashboard_summary(self, current_user: User) -> Dict:
        """Backward-compatible monolithic payload for existing clients: current UTC month."""
        now_utc = datetime.now(timezone.utc)
        y, m = now_utc.year, now_utc.month
        k = self._repo.fetch_kpis(year=y, month=m, now_utc=now_utc)
        # Same cumulative 12m series as pre-split dashboard (avoids changing legacy chart semantics).
        tr = self._repo.fetch_rolling_cumulative_12m_utc()
        lead_labels, lead_vals = self._repo.fetch_lead_source_breakdown()
        pr, _ = self._repo.fetch_top_properties_by_views(
            period=PropertyPerformancePeriod.MONTHLY.value,
            page=1,
            limit=5,
            agent_id=None,
        )
        d = _kpi_to_public_dict(k)
        # New: summary counts (exclude deleted only; include inactive).
        d.update(self._repo.fetch_total_user_counts_by_role())
        effective_admin_id = self._resolve_effective_admin_id(current_user)
        d["totalAgentCount"] = self._repo.count_active_assigned_agents_for_admin(
            admin_id=effective_admin_id
        )
        activity: List[ActivityLogItem] = self._repo.fetch_recent_activity_for_user(
            user_id=effective_admin_id, limit=5
        )
        d["recentActivity"] = _activity_items_to_public(activity)
        d["monthLabels"] = tr.month_labels
        d["userGrowthSeries"] = tr.user_growth_series
        d["listingGrowthSeries"] = tr.listing_growth_series
        d["leadGrowthSeries"] = tr.lead_growth_series
        d["leadSourceLabels"] = lead_labels
        d["leadSourceValues"] = lead_vals
        d["propertyPerformanceSeries"] = _build_property_items(pr)
        return d

    def get_recent_activity(self, current_user: User, *, limit: int = 5) -> List[dict]:
        """Return recent activity items for the effective admin user (max 50; default 5)."""
        effective_admin_id = self._resolve_effective_admin_id(current_user)
        activity: List[ActivityLogItem] = self._repo.fetch_recent_activity_for_user(
            user_id=effective_admin_id, limit=limit
        )
        return _activity_items_to_public(activity)
