"""Service layer for the lead analytics dashboard summary.

Resolves the caller's scope (admin = all leads, agent = own assigned leads),
validates the requested range, delegates aggregation to
``LeadDashboardRepository`` and shapes the result into typed DTO-ready dicts.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException

from app.models.user import User
from app.repositories.lead_dashboard_repository import (
    LeadComplianceMetrics,
    LeadDashboardMetrics,
    LeadDashboardRepository,
)
from app.utils.constants import ErrorMessages, LeadDashboardConstants, UserRoles
from app.utils.status_codes import HTTPStatus


def _round(value: float, places: str = "0.01") -> float:
    return float(Decimal(str(value or 0.0)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


class LeadDashboardService:
    """Build the lead dashboard summary payload for the authenticated user."""

    def __init__(self, repo: LeadDashboardRepository) -> None:
        self._repo = repo

    def get_dashboard_summary(self, *, actor: User, range_key: str) -> dict[str, Any]:
        range_key = self._validate_range(range_key)
        scope, actor_id = self._resolve_scope(actor)

        metrics = self._repo.get_metrics(scope=scope, range_key=range_key, actor_id=actor_id)
        return self._build_payload(metrics)

    def get_compliance_report(self, *, actor: User) -> dict[str, Any]:
        scope, actor_id = self._resolve_scope(actor)
        metrics = self._repo.get_compliance_metrics(scope=scope, actor_id=actor_id)
        return self._build_compliance_payload(metrics)

    @staticmethod
    def _validate_range(range_key: str | None) -> str:
        normalized = (range_key or LeadDashboardConstants.DEFAULT_RANGE).strip().lower()
        if normalized not in LeadDashboardConstants.ALLOWED_RANGES:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_LEAD_DASHBOARD_RANGE,
            )
        return normalized

    @staticmethod
    def _resolve_scope(actor: User) -> tuple[str, Any]:
        roles = {role.name for role in actor.roles}
        if UserRoles.ADMIN in roles:
            return "admin", None
        if UserRoles.AGENT in roles:
            return "agent", actor.id
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=ErrorMessages.UNAUTHORIZED_ACCESS,
        )

    def _build_payload(self, metrics: LeadDashboardMetrics) -> dict[str, Any]:
        counts = metrics.status_counts
        total = metrics.total_leads
        new_leads = counts.get(LeadDashboardConstants.STATUS_NEW, 0)
        mql = counts.get(LeadDashboardConstants.STATUS_IN_PROGRESS, 0)
        sql = counts.get(LeadDashboardConstants.STATUS_REQUEST_FOR_CLOSE, 0)
        converted = counts.get(LeadDashboardConstants.STATUS_CLOSED, 0)
        opportunities = mql + sql

        conversion_rate = _round((converted / total) * 100) if total else 0.0

        return {
            "totalLeads": total,
            "newLeads": new_leads,
            "mql": mql,
            "sql": sql,
            "opportunities": opportunities,
            "convertedCustomers": converted,
            "averageLeadAgingDays": _round(metrics.avg_aging_days, "0.1"),
            "slaBreachCount": metrics.sla_breach_count,
            "conversionRate": conversion_rate,
            "averageResponseTimeHours": _round(metrics.avg_response_hours, "0.1"),
            "funnel": self._build_funnel(counts),
            "sourcePerformance": self._build_source_performance(metrics.source_performance),
            "agingBuckets": self._build_aging_buckets(metrics.aging_buckets),
            "trend": [
                {
                    "period": point["period"],
                    "totalLeads": int(point.get("total_leads", 0)),
                    "converted": int(point.get("converted", 0)),
                }
                for point in metrics.trend
            ],
        }

    def _build_compliance_payload(self, metrics: LeadComplianceMetrics) -> dict[str, Any]:
        total = metrics.total_leads
        compliant = max(total - metrics.sla_breach_count, 0)
        sla_compliance_rate = _round((compliant / total) * 100) if total else 0.0

        active = metrics.active_total
        follow_up_rate = _round((metrics.follow_up_compliant / active) * 100) if active else 0.0

        return {
            "slaBreachCount": metrics.sla_breach_count,
            "slaComplianceRate": sla_compliance_rate,
            "averageResponseTimeHours": _round(metrics.avg_response_hours, "0.1"),
            "followUpComplianceRate": follow_up_rate,
            "missingSourceCount": metrics.missing_source_count,
            "duplicateCount": metrics.duplicate_count,
            "missingLostReasonCount": metrics.missing_lost_reason_count,
        }

    @staticmethod
    def _build_funnel(counts: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {
                "stage": key,
                "label": label,
                "count": sum(counts.get(status, 0) for status in statuses),
            }
            for key, label, statuses in LeadDashboardConstants.FUNNEL_STAGES
        ]

    @staticmethod
    def _build_source_performance(rows: list[dict]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            total = int(row.get("total_leads", 0))
            converted = int(row.get("converted", 0))
            rate = _round((converted / total) * 100) if total else 0.0
            out.append(
                {
                    "source": row.get("source"),
                    "totalLeads": total,
                    "converted": converted,
                    "conversionRate": rate,
                }
            )
        return out

    @staticmethod
    def _build_aging_buckets(buckets: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"bucket": label, "count": int(buckets.get(label, 0))}
            for label, _upper in LeadDashboardConstants.AGING_BUCKETS
        ]
