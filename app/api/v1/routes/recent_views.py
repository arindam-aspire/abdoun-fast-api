"""Endpoints for per-user recently viewed properties."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.recent_views import get_recent_view_service
from app.api.v1.deps.security import get_current_user
from app.domains.shared.pagination import calculate_pagination
from app.models.user import User
from app.schemas.recent_view import (
    RecentViewsListResponse,
    RecentViewUpsertRequest,
)
from app.services.recent_view_service import RecentViewService
from app.utils.constants import SuccessMessages
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus

router = APIRouter()


@router.post(
    "/recent-views",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def add_recent_view(
    body: RecentViewUpsertRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[RecentViewService, Depends(get_recent_view_service)],
):
    """Add or refresh a recent property for the current user."""
    service.add_or_refresh_from_request(user_id=current_user.id, body=body)
    return create_success_response(data=True, message=SuccessMessages.RECENT_VIEW_UPDATED)


@router.get(
    "/recent-views",
    response_model=StandardResponse[RecentViewsListResponse],
    status_code=HTTPStatus.OK,
)
def list_recent_views(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[RecentViewService, Depends(get_recent_view_service)],
):
    """Return latest 10 recently viewed properties for the current user."""
    recent_views = service.list_recent_views(user_id=current_user.id)
    pm = calculate_pagination(page=1, page_size=max(recent_views.total, 1), total=recent_views.total)
    return create_success_response(data=recent_views, message=None, pagination=pm)


@router.delete(
    "/recent-views",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def clear_recent_views(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[RecentViewService, Depends(get_recent_view_service)],
):
    """Clear all recent views for the current user."""
    service.clear_recent_views(user_id=current_user.id)
    return create_success_response(data=True, message=SuccessMessages.RECENT_VIEWS_CLEARED)


@router.delete(
    "/recent-views/{property_hash}",
    response_model=StandardResponse[bool],
    status_code=HTTPStatus.OK,
)
def remove_recent_view(
    property_hash: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[RecentViewService, Depends(get_recent_view_service)],
):
    """Remove one property from current user's recent views."""
    removed = service.remove_recent_view(
        user_id=current_user.id,
        property_hash=property_hash,
    )
    return create_success_response(data=removed, message=SuccessMessages.RECENT_VIEW_REMOVED)
