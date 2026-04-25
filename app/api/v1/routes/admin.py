"""Platform admin routes (global KPIs, not per-admin agent scope)."""

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.admin_dashboard import get_admin_dashboard_service
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.admin_dashboard import (
    AdminDashboardKpisResponse,
    AdminDashboardPropertyPerformanceResponse,
    AdminDashboardSummaryResponse,
    AdminDashboardTrendsResponse,
    PropertyPerformanceItem,
)
from app.services.admin_dashboard_service import AdminDashboardService
from app.utils.constants import UserRoles
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()

_MONTH_RE = r"^(20[0-9][0-9])-(0[1-9]|1[0-2])$"


@router.get("/dashboard/kpis")
def get_admin_dashboard_kpis(
    _current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
    month: Annotated[str, Query(description="Reporting month (UTC), e.g. 2026-04", pattern=_MONTH_RE)],
) -> StandardResponse[AdminDashboardKpisResponse]:
    """KPIs for a full calendar month; MoM compares to the full previous month."""
    data = service.get_kpis(month=month)
    return create_success_response(data=AdminDashboardKpisResponse(**data), message=None)


@router.get("/dashboard/trends")
def get_admin_dashboard_trends(
    _current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
    months: Annotated[int, Query(description="Trailing month count (1-24).", ge=1, le=24)] = 12,
    endMonth: Annotated[
        Optional[str],
        Query(description="Optional anchor month (UTC) for the last bucket, YYYY-MM. Default: current month."),
    ] = None,
) -> StandardResponse[AdminDashboardTrendsResponse]:
    """User, listing, and lead counts per calendar month (not cumulative), oldest first."""
    data = service.get_trends(months=months, end_month=endMonth)
    return create_success_response(data=AdminDashboardTrendsResponse(**data), message=None)


@router.get("/dashboard/property-performance")
def get_admin_property_performance(
    _current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
    limit: Annotated[int, Query(description="Max rows to return", ge=1, le=100)] = 5,
    agentId: Annotated[
        Optional[uuid.UUID],
        Query(description="If set, restrict to this agent’s listings only."),
    ] = None,
) -> StandardResponse[AdminDashboardPropertyPerformanceResponse]:
    """Top properties by view count (server: last 30 days, UTC) for the bar chart."""
    data = service.get_property_performance(limit=limit, agent_id=agentId)
    return create_success_response(
        data=AdminDashboardPropertyPerformanceResponse(
            items=[PropertyPerformanceItem(**i) for i in data["items"]]
        ),
        message=None,
    )


@router.get("/dashboard/summary")
def get_admin_dashboard_summary(
    _current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
) -> StandardResponse[AdminDashboardSummaryResponse]:
    """Legacy: all dashboard widgets in one payload (current UTC month KPIs, 12-month trends, etc.)."""
    data = service.get_dashboard_summary()
    return create_success_response(data=AdminDashboardSummaryResponse(**data), message=None)
