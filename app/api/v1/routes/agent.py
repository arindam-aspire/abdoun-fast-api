"""Agent-only endpoints (singular /agent prefix)."""

import math
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.admin_dashboard import get_admin_dashboard_service
from app.core.permissions import require_role
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
    limit: Annotated[
        PropertyPerformancePeriod,
        Query(
            description=(
                "View window: all (default), weekly, monthly, yearly "
                "(trailing 7 / 30 / 365 days by wall-clock interval; case-insensitive)."
            )
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
) -> StandardResponse[AdminDashboardPropertyPerformanceResponse]:
    """Agent: top properties (owned by the authenticated agent) by view count; paginated."""
    data = service.get_property_performance(
        period=limit, page=page, limit=page_size, agent_id=current_user.id
    )
    lim = int(data["limit"])
    total_items = int(data["totalItems"])
    total_pages = math.ceil(total_items / lim) if total_items > 0 else 0
    return create_success_response(
        data=AdminDashboardPropertyPerformanceResponse(
            items=[PropertyPerformanceItem(**i) for i in data["items"]],
            pagination=PaginationInfo(
                page=int(data["page"]),
                limit=lim,
                totalItems=total_items,
                totalPages=total_pages,
            ),
        ),
        message=None,
    )

