"""Platform admin routes (global KPIs, not per-admin agent scope)."""

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.admin_dashboard import get_admin_dashboard_service
from app.core.permissions import require_role
from app.domains.shared.pagination import calculate_pagination
from app.models.user import User
from app.schemas.admin_dashboard import (
    AdminDashboardKpisResponse,
    AdminDashboardPropertyPerformanceResponse,
    AdminDashboardRecentActivityItem,
    AdminDashboardSummaryResponse,
    AdminDashboardTrendsResponse,
    PropertyPerformanceItem,
    PropertyPerformancePeriod,
)
from app.schemas.user import PaginationInfo
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


@router.get("/property-performance")
def get_admin_property_performance(
    _current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
    period: Annotated[
        PropertyPerformancePeriod,
        Query(
            description=(
                "View window: all (default), weekly, monthly, yearly "
                "(trailing 7 / 30 / 365 days by wall-clock interval; case-insensitive)."
            ),
        ),
    ] = PropertyPerformancePeriod.ALL,
    page: Annotated[int, Query(ge=1, description="1-based page index.")] = 1,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            description="Properties per page.",
            ge=1,
            le=100,
        ),
    ] = 5,
    # Compatibility alias (older clients used `limit` for the period/window)
    agentId: Annotated[
        Optional[uuid.UUID],
        Query(description="If set, restrict to this agent’s listings only."),
    ] = None,
) -> StandardResponse[AdminDashboardPropertyPerformanceResponse]:
    """Top properties by view count for the bar chart; paginated (see ``pagination`` in the payload)."""
    data = service.get_property_performance(
        period=period, page=page, limit=page_size, agent_id=agentId
    )
    total_items = int(data["totalItems"])
    meta = calculate_pagination(page=int(data["page"]), page_size=page_size, total=total_items)
    return create_success_response(
        data=AdminDashboardPropertyPerformanceResponse(
            items=[PropertyPerformanceItem(**i) for i in data["items"]],
            pagination=PaginationInfo(
                page=meta.page,
                pageSize=meta.page_size,
                total=total_items,
                totalPages=meta.total_pages,
                hasNext=meta.has_next,
                hasPrevious=meta.has_previous,
            ),
        ),
        message=None,
        pagination=meta,
    )


@router.get("/dashboard/summary")
def get_admin_dashboard_summary(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
) -> StandardResponse[AdminDashboardSummaryResponse]:
    """Legacy: all dashboard widgets in one payload (current UTC month KPIs, 12-month trends, etc.)."""
    data = service.get_dashboard_summary(current_user)
    return create_success_response(data=AdminDashboardSummaryResponse(**data), message=None)


@router.get("/dashboard/recent-activity")
def get_admin_dashboard_recent_activity(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
) -> StandardResponse[list[AdminDashboardRecentActivityItem]]:
    """Recent activity timeline items for the authenticated admin (max 5).

    Backward-compatible alias for `/admin/recent-activity`.
    """
    items = service.get_recent_activity(current_user, limit=5)
    return create_success_response(
        data=[AdminDashboardRecentActivityItem(**i) for i in items],
        message=None,
    )


@router.get("/recent-activity")
def get_admin_recent_activity(
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
) -> StandardResponse[list[AdminDashboardRecentActivityItem]]:
    """Recent activity timeline items for the authenticated admin (max 5)."""
    items = service.get_recent_activity(current_user, limit=5)
    return create_success_response(
        data=[AdminDashboardRecentActivityItem(**i) for i in items],
        message=None,
    )
