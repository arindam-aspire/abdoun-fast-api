"""Business logic for property favorites endpoints."""
import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.domains.shared.pagination import calculate_pagination
from app.models.user_property_favorite import UserPropertyFavorite
from app.repositories.favorite_repository import FavoriteRepository
from app.schemas.property_favorites import (
    FavoriteBulkCreateResponse,
    FavoriteBulkSkippedItem,
    FavoriteListResponse,
    FavoriteResponse,
)
from app.schemas.property import PropertySearchResultExtended
from app.services.media_url_signer import MediaUrlSigner
from app.utils.constants import ErrorMessages
from app.utils.status_codes import HTTPStatus


class FavoriteService:
    """Service layer for user property favorites."""

    def __init__(self, repository: FavoriteRepository, *, media_url_signer: MediaUrlSigner | None = None) -> None:
        self._repo = repository
        self._media_url_signer = media_url_signer

    def _property_search_row(self, property_obj: object) -> PropertySearchResultExtended:
        row = PropertySearchResultExtended.from_orm_obj(property_obj)
        if self._media_url_signer is not None:
            self._media_url_signer.sign_search_result_extended(row)
        return row

    def _resolve_property_id_from_hash(self, property_hash: int) -> uuid.UUID:
        property_id = self._repo.find_property_uuid_by_hash(property_hash)
        if not property_id:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.PROPERTY_NOT_FOUND,
            )
        return property_id

    def _ensure_active_property(self, property_id: uuid.UUID):
        property_obj = self._repo.get_property_by_id(property_id)
        if not property_obj:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.PROPERTY_NOT_FOUND,
            )
        if property_obj.property_status_id != 1:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.ONLY_ACTIVE_PROPERTIES_CAN_BE_FAVORITED,
            )
        return property_obj

    def add_favorite(self, *, user: User, property_hash: int) -> FavoriteResponse:
        property_id = self._resolve_property_id_from_hash(property_hash)
        property_obj = self._ensure_active_property(property_id)

        existing = self._repo.get_favorite_by_user_and_property(
            user_id=user.id, property_id=property_id
        )
        if existing:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.PROPERTY_ALREADY_FAVORITED,
            )

        favorite = UserPropertyFavorite(user_id=user.id, property_id=property_id)
        try:
            self._repo.create_favorite(favorite)
            self._repo.commit()
            self._repo.refresh(favorite)
            return FavoriteResponse(
                id=favorite.id,
                user_id=favorite.user_id,
                property_hash=int(property_obj.property_hash),
                property=self._property_search_row(property_obj),
            )
        except IntegrityError:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.PROPERTY_ALREADY_FAVORITED,
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

    def add_favorites_bulk(
        self, *, user: User, property_hashes: list[int]
    ) -> FavoriteBulkCreateResponse:
        unique_property_hashes: list[int] = list(dict.fromkeys(property_hashes))
        unique_property_ids: list[uuid.UUID] = []
        hash_to_property_id: dict[int, uuid.UUID] = {}
        skipped: list[FavoriteBulkSkippedItem] = []

        for property_hash in unique_property_hashes:
            property_id = self._repo.find_property_uuid_by_hash(property_hash)
            if not property_id:
                skipped.append(
                    FavoriteBulkSkippedItem(
                        property_hash=property_hash,
                        reason=ErrorMessages.PROPERTY_NOT_FOUND,
                    )
                )
                continue
            unique_property_ids.append(property_id)
            hash_to_property_id[property_hash] = property_id

        properties = self._repo.list_properties_by_ids(unique_property_ids)
        property_map = {property_obj.id: property_obj for property_obj in properties}
        existing_favorite_ids = self._repo.get_user_favorite_property_ids(
            user_id=user.id, property_ids=unique_property_ids
        )

        favorites_to_add: list[tuple[UserPropertyFavorite, object]] = []

        try:
            for property_hash in unique_property_hashes:
                property_id = hash_to_property_id.get(property_hash)
                if not property_id:
                    continue
                property_obj = property_map.get(property_id)
                if not property_obj:
                    skipped.append(
                        FavoriteBulkSkippedItem(
                            property_hash=property_hash,
                            reason=ErrorMessages.PROPERTY_NOT_FOUND,
                        )
                    )
                    continue

                if property_obj.property_status_id != 1:
                    skipped.append(
                        FavoriteBulkSkippedItem(
                            property_hash=property_hash,
                            reason=ErrorMessages.ONLY_ACTIVE_PROPERTIES_CAN_BE_FAVORITED,
                        )
                    )
                    continue

                if property_id in existing_favorite_ids:
                    skipped.append(
                        FavoriteBulkSkippedItem(
                            property_hash=property_hash,
                            reason=ErrorMessages.PROPERTY_ALREADY_FAVORITED,
                        )
                    )
                    continue

                favorite = UserPropertyFavorite(user_id=user.id, property_id=property_id)
                self._repo.create_favorite(favorite)
                favorites_to_add.append((favorite, property_obj))

            self._repo.commit()
            added = [
                FavoriteResponse(
                    id=favorite.id,
                    user_id=favorite.user_id,
                    property_hash=int(property_obj.property_hash),
                    property=self._property_search_row(property_obj),
                )
                for favorite, property_obj in favorites_to_add
            ]
            return FavoriteBulkCreateResponse(added=added, skipped=skipped)
        except IntegrityError:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.PROPERTY_ALREADY_FAVORITED,
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

    def list_favorites(self, *, user: User, page: int, page_size: int) -> FavoriteListResponse:
        items = self._repo.list_user_favorites(user_id=user.id)
        response_items = [
            FavoriteResponse(
                id=item.id,
                user_id=item.user_id,
                property_hash=int(item.property.property_hash),
                property=self._property_search_row(item.property),
            )
            for item in items
            if item.property is not None
        ]
        total = len(response_items)
        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        paged_items = response_items[meta.offset : meta.offset + meta.page_size]
        return FavoriteListResponse(
            items=paged_items,
            total=total,
            page=meta.page,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
        )

    def remove_favorite(self, *, user: User, property_hash: int) -> bool:
        property_id = self._resolve_property_id_from_hash(property_hash)
        favorite = self._repo.get_favorite_by_user_and_property(
            user_id=user.id, property_id=property_id
        )
        if not favorite:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.FAVORITE_NOT_FOUND,
            )
        try:
            self._repo.delete_favorite(favorite)
            self._repo.commit()
            return True
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

