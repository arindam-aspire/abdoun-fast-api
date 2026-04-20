"""Service for recently viewed properties business logic."""

import uuid
from typing import List

from fastapi import HTTPException

from app.models.recently_viewed_property import RecentlyViewedProperty
from app.repositories.recent_view_repository import RecentViewRepository
from app.schemas.property import PropertySearchResultExtended
from app.schemas.recent_view import RecentViewItem, RecentViewsListResponse
from app.utils.constants import ErrorMessages
from app.utils.status_codes import HTTPStatus

RECENT_VIEWS_LIMIT = 10


class RecentViewService:
    """Business logic for upsert/list/clear recently viewed properties."""

    def __init__(self, repository: RecentViewRepository) -> None:
        self._repo = repository

    def add_or_refresh(self, *, user_id: uuid.UUID, property_id: uuid.UUID) -> None:
        """Add property to recent views or refresh timestamp if already exists."""
        if not self._repo.ensure_user_exists_and_lock(user_id):
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )

        if not self._repo.property_exists(property_id):
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.PROPERTY_NOT_FOUND,
            )

        try:
            self._repo.upsert_recent_view(user_id=user_id, property_id=property_id)
            self._repo.trim_to_limit(user_id=user_id, limit=RECENT_VIEWS_LIMIT)
            self._repo.commit()
        except HTTPException:
            self._repo.rollback()
            raise
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f"{ErrorMessages.RECENT_VIEWS_UPDATE_FAILED}: {exc}",
            ) from exc

    def list_recent_views(self, *, user_id: uuid.UUID) -> RecentViewsListResponse:
        items: List[RecentlyViewedProperty] = self._repo.list_recent_views(
            user_id=user_id,
            limit=RECENT_VIEWS_LIMIT,
        )
        response_items = [
            RecentViewItem(
                id=item.id,
                user_id=item.user_id,
                property_hash=int(item.property.property_hash),
                property_id=item.property_id,
                viewed_at=item.viewed_at,
                property=PropertySearchResultExtended.from_orm_obj(item.property),
            )
            for item in items
            if item.property is not None
        ]
        return RecentViewsListResponse(items=response_items, total=len(response_items))

    def clear_recent_views(self, *, user_id: uuid.UUID) -> int:
        try:
            deleted = self._repo.clear_recent_views(user_id=user_id)
            self._repo.commit()
            return deleted
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f"{ErrorMessages.RECENT_VIEWS_CLEAR_FAILED}: {exc}",
            ) from exc

    def remove_recent_view(self, *, user_id: uuid.UUID, property_hash: int) -> bool:
        """Remove one recent view by property hash/id used in public URLs."""
        property_id = self._repo.find_property_uuid_by_hash(property_hash=property_hash)
        if property_id is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.PROPERTY_NOT_FOUND,
            )

        try:
            deleted = self._repo.delete_recent_view_by_property_id(
                user_id=user_id,
                property_id=property_id,
            )
            self._repo.commit()
            return deleted > 0
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f"{ErrorMessages.RECENT_VIEWS_CLEAR_FAILED}: {exc}",
            ) from exc
