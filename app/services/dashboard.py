from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.dashboard import (
    DashboardScope,
    get_closed_deals_count,
    get_health_context,
    get_lead_counts,
    get_lead_growth,
    get_lead_sources,
    get_listing_counts,
    get_listing_growth,
    get_pending_agency_counts,
    get_recent_activity,
    get_user_counts,
    get_user_growth,
)
from app.schemas.dashboard import DashboardActivity, DashboardSummaryData
from app.services.property_submissions import PENDING_APPROVAL_STATUS
from app.utils.status_codes import STATUS_FORBIDDEN


LEAD_SOURCE_ORDER = (
    "EMAIL_FORM",
    "PHONE",
    "WHATSAPP",
    "MANUAL_ADMIN",
    "AGENT_MANUAL",
    "OFFLINE_MANUAL",
)
ALLOWED_TONES = {"info", "success", "warning", "error"}


def _month_start(value: datetime) -> datetime:
    return datetime(value.year, value.month, 1, tzinfo=timezone.utc)


def _shift_month(value: datetime, offset: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    return datetime(year, zero_based_month + 1, 1, tzinfo=timezone.utc)


def _mom_delta(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _scope_for_context(
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> DashboardScope:
    role_names = {role.casefold() for role in roles}
    if "super_admin" in role_names:
        return DashboardScope(kind="super_admin", user_id=user_id)
    if role_names & {"admin", "agency", "agency_admin"}:
        return DashboardScope(
            kind="agency_admin",
            user_id=user_id,
            agency_id=agency_id,
        )
    if "agent" in role_names:
        return DashboardScope(kind="agent", user_id=user_id, agency_id=agency_id)
    raise HTTPException(
        status_code=STATUS_FORBIDDEN,
        detail="Insufficient permissions",
    )


def _month_key(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    return str(value)[:7]


def _aligned_series(
    rows: list[tuple[Any, int]],
    month_starts: list[datetime],
) -> list[int]:
    counts = {_month_key(month): count for month, count in rows}
    return [counts.get(month.strftime("%Y-%m"), 0) for month in month_starts]


def _activity_type(activity_type: str | None) -> str:
    value = (activity_type or "").casefold()
    if any(token in value for token in ("approval", "approved", "rejected", "review")):
        return "approval"
    if "deal" in value or "closure" in value:
        return "deal"
    if "lead" in value:
        return "lead"
    if "agent" in value:
        return "agent"
    if "property" in value or "listing" in value or "submission" in value:
        return "listing"
    return "user"


def _activity_tone(activity_type: str | None, tone: str | None) -> str:
    normalized = (tone or "").casefold()
    if normalized in ALLOWED_TONES:
        return normalized
    value = (activity_type or "").casefold()
    if any(token in value for token in ("approved", "active", "accepted", "closed")):
        return "success"
    if any(token in value for token in ("rejected", "declined", "deleted", "failed")):
        return "error"
    if any(token in value for token in ("pending", "requested", "submitted", "invited")):
        return "warning"
    return "info"


def _serialize_activities(rows) -> list[DashboardActivity]:
    return [
        DashboardActivity(
            id=str(row.id),
            type=_activity_type(row.activity_type),
            text=row.message or (row.activity_type or "Activity").replace("_", " ").title(),
            time=row.created_at.isoformat() if row.created_at else "",
            tone=_activity_tone(row.activity_type, row.tone),
        )
        for row in rows
    ]


def _health_alerts(
    db: Session,
    *,
    scope: DashboardScope,
    pending_approvals: int,
) -> list[str]:
    user, profile, agency = get_health_context(db, scope=scope)
    alerts: list[str] = []

    if scope.kind == "agent" and (
        profile is None or not profile.identity_document_s3_link
    ):
        alerts.append("LEGAL_DOCUMENT_MISSING")
    elif scope.kind == "agency_admin" and (
        agency is None or not agency.legal_document_s3_link
    ):
        alerts.append("LEGAL_DOCUMENT_MISSING")

    profile_incomplete = user is None or not user.full_name or not user.phone_number
    if scope.kind == "agent":
        profile_incomplete = profile_incomplete or profile is None or not profile.service_area
    if profile_incomplete:
        alerts.append("PROFILE_INCOMPLETE")

    if user and not user.is_email_verified:
        alerts.append("EMAIL_NOT_VERIFIED")
    if user and user.phone_number and not user.is_phone_verified:
        alerts.append("PHONE_NOT_VERIFIED")
    if pending_approvals > 0 and scope.kind != "agent":
        alerts.append("PENDING_APPROVALS")
    return alerts


def dashboard_summary(
    db: Session,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
    now: datetime | None = None,
) -> DashboardSummaryData:
    now = now or datetime.now(timezone.utc)
    current_start = _month_start(now)
    next_start = _shift_month(current_start, 1)
    previous_start = _shift_month(current_start, -1)
    series_start = _shift_month(current_start, -11)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    tomorrow_start = today_start + timedelta(days=1)
    month_starts = [_shift_month(series_start, offset) for offset in range(12)]
    scope = _scope_for_context(
        user_id=user_id,
        roles=roles,
        agency_id=agency_id,
    )

    user_counts = get_user_counts(
        db,
        scope=scope,
        current_start=current_start,
        next_start=next_start,
        previous_start=previous_start,
        today_start=today_start,
        tomorrow_start=tomorrow_start,
    )
    listing_counts = get_listing_counts(
        db,
        scope=scope,
        current_start=current_start,
        next_start=next_start,
        previous_start=previous_start,
        today_start=today_start,
        tomorrow_start=tomorrow_start,
        pending_status=PENDING_APPROVAL_STATUS,
    )
    lead_counts = get_lead_counts(
        db,
        scope=scope,
        current_start=current_start,
        next_start=next_start,
        previous_start=previous_start,
    )

    pending_approvals = 0
    pending_approvals_today = 0
    if scope.kind == "agency_admin":
        pending_approvals = (
            listing_counts["pending"] + user_counts["pending_agents"]
        )
        pending_approvals_today = (
            listing_counts["pending_today"] + user_counts["pending_agents_today"]
        )
    if scope.kind == "super_admin":
        pending_approvals, pending_approvals_today = get_pending_agency_counts(
            db,
            today_start=today_start,
            tomorrow_start=tomorrow_start,
        )

    user_growth = get_user_growth(
        db,
        scope=scope,
        start=series_start,
        end=next_start,
    )
    listing_growth = get_listing_growth(
        db,
        scope=scope,
        start=series_start,
        end=next_start,
    )
    lead_growth = get_lead_growth(
        db,
        scope=scope,
        start=series_start,
        end=next_start,
    )
    source_counts = dict(get_lead_sources(db, scope=scope))
    source_labels = [source for source in LEAD_SOURCE_ORDER if source in source_counts]
    source_labels.extend(sorted(set(source_counts) - set(source_labels)))

    return DashboardSummaryData(
        month=current_start.strftime("%Y-%m"),
        totalRegisterUserCount=user_counts["total_users"],
        totalAgentCount=user_counts["total_agents"],
        totalAdminCount=user_counts["total_admins"],
        registerUsersThisMonth=user_counts["users_current"],
        registerUsersMoMDelta=_mom_delta(
            user_counts["users_current"],
            user_counts["users_previous"],
        ),
        agentsThisMonth=user_counts["agents_current"],
        agentsMoMDelta=_mom_delta(
            user_counts["agents_current"],
            user_counts["agents_previous"],
        ),
        pendingApprovals=pending_approvals,
        pendingApprovalsToday=pending_approvals_today,
        listingsThisMonth=listing_counts["current"],
        listingsMoMDelta=_mom_delta(
            listing_counts["current"],
            listing_counts["previous"],
        ),
        leadsThisMonth=lead_counts["current"],
        leadsMoMDelta=_mom_delta(
            lead_counts["current"],
            lead_counts["previous"],
        ),
        closedDealsThisMonth=get_closed_deals_count(
            db,
            scope=scope,
            current_start=current_start,
            next_start=next_start,
        ),
        monthLabels=[calendar.month_abbr[month.month] for month in month_starts],
        userGrowthSeries=_aligned_series(user_growth, month_starts),
        listingGrowthSeries=_aligned_series(listing_growth, month_starts),
        leadGrowthSeries=_aligned_series(lead_growth, month_starts),
        leadSourceLabels=source_labels,
        leadSourceValues=[source_counts[source] for source in source_labels],
        recentActivity=_serialize_activities(
            get_recent_activity(db, scope=scope, limit=10)
        ),
        healthAlerts=_health_alerts(
            db,
            scope=scope,
            pending_approvals=pending_approvals,
        ),
    )
