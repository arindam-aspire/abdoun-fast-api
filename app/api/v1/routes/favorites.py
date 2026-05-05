"""Authenticated favorites endpoints for user property favorites."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.favorites import get_favorite_service
from app.api.v1.deps.security import get_current_user
from app.domains.shared.pagination import calculate_pagination
from app.models.user import User
from app.schemas.property_favorites import (
    FavoriteBulkCreateRequest,
    FavoriteBulkCreateResponse,
    FavoriteCreateRequest,
    FavoriteListResponse,
    FavoriteResponse,
)
from app.services.favorite_service import FavoriteService
from app.utils.constants import SuccessMessages
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.post("", response_model=StandardResponse[FavoriteResponse])
def add_favorite(
    body: FavoriteCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
):
    """Add a property to the current user's favorites."""
    favorite = service.add_favorite(user=current_user, property_hash=body.property_hash)
    return create_success_response(
        data=favorite,
        message=SuccessMessages.PROPERTY_FAVORITED,
    )


@router.post("/bulk", response_model=StandardResponse[FavoriteBulkCreateResponse])
def add_favorites_bulk(
    body: FavoriteBulkCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
):
    """Add multiple properties to the current user's favorites."""
    result = service.add_favorites_bulk(
        user=current_user, property_hashes=body.property_hashes
    )
    return create_success_response(
        data=result,
        message=SuccessMessages.PROPERTIES_FAVORITED_BULK,
    )


@router.get("", response_model=StandardResponse[FavoriteListResponse])
def list_favorites(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    page: Annotated[int, Query(ge=1, description="1-based page index.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize", description="Items per page.")] = 20,
):
    """List favorites for the current user with page-based pagination."""
    favorites = service.list_favorites(user=current_user, page=page, page_size=page_size)
    pm = calculate_pagination(page=favorites.page, page_size=favorites.pageSize, total=favorites.total)
    return create_success_response(data=favorites, message=None, pagination=pm)


@router.delete("/{property_hash}", response_model=StandardResponse[bool])
def remove_favorite(
    property_hash: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
):
    """Remove a property from the current user's favorites."""
    removed = service.remove_favorite(user=current_user, property_hash=property_hash)
    return create_success_response(
        data=removed,
        message=SuccessMessages.PROPERTY_UNFAVORITED,
    )

