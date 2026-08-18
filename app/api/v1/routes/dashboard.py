from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, require_any_role
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard import dashboard_summary


router = APIRouter()
DashboardContext = Annotated[
    RequestContext,
    Depends(require_any_role("super_admin", "admin", "agency_admin", "agent")),
]


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    context: DashboardContext,
    db: DBSessionDep,
) -> DashboardSummaryResponse:
    return DashboardSummaryResponse(
        data=dashboard_summary(
            db,
            user_id=context.user_id,
            roles=context.roles,
            agency_id=context.agency_id,
        )
    )
