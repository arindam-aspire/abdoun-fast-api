"""Agent-only endpoints (singular /agent prefix)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.admin_dashboard import get_admin_dashboard_service
from app.core.permissions import require_role
from app.domains.shared.pagination import calculate_pagination
from app.models.user import User
from app.schemas.admin_dashboard import (
    AdminDashboardPropertyPerformanceResponse,
    PropertyPerformanceItem,
    PropertyPerformancePeriod,
)
from app.schemas.user import PaginationInfo
from app.services.admin_dashboard_service import AdminDashboardService
from app.utils.constants import UserRoles
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.get("/property-performance")
def get_agent_property_performance(
    current_user: Annotated[User, require_role(UserRoles.AGENT)],
    service: Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)],
    period: Annotated[
        PropertyPerformancePeriod,
        Query(
            description=(
                "View window: all (default), weekly, monthly, yearly "
                "(trailing 7 / 30 / 365 days by wall-clock interval; case-insensitive)."
            )
        ),
    ] = PropertyPerformancePeriod.ALL,
    limit: Annotated[
        PropertyPerformancePeriod | None,
        Query(
            deprecated=True,
            description="Deprecated alias for `period`.",
        ),
    ] = None,
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
) -> StandardResponse[AdminDashboardPropertyPerformanceResponse]:
    """Agent: top properties (owned by the authenticated agent) by view count; paginated."""
    effective_period = limit or period
    data = service.get_property_performance(
        period=effective_period, page=page, limit=page_size, agent_id=current_user.id
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

