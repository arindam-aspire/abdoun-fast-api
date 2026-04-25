"""Business logic for user saved searches."""
import uuid
from urllib.parse import urlencode
from typing import List

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.models.user_saved_search import UserSavedSearch
from app.repositories.saved_search_repository import SavedSearchRepository
from app.schemas.property import PropertySearchResultExtended
from app.services.media_url_signer import MediaUrlSigner
from app.schemas.saved_search import (
    SavedSearchCreateRequest,
    SavedSearchExecutionResponse,
    SavedSearchResponse,
    SavedSearchUpdateRequest,
)
from app.utils.constants import ErrorMessages
from app.utils.status_codes import HTTPStatus


class SavedSearchService:
    """Service layer for saved-search CRUD and execution."""

    def __init__(self, repository: SavedSearchRepository, *, media_url_signer: MediaUrlSigner | None = None) -> None:
        self._repo = repository
        self._media_url_signer = media_url_signer

    @staticmethod
    def _build_query_string(search_criteria: dict) -> str:
        if not search_criteria:
            return ""
        criteria_items = []
        for key in sorted(search_criteria.keys()):
            value = search_criteria[key]
            if isinstance(value, list):
                criteria_items.append((key, [str(item) for item in value]))
            elif value is None:
                continue
            else:
                criteria_items.append((key, str(value)))
        flattened_items = []
        for key, value in criteria_items:
            if isinstance(value, list):
                for item in value:
                    flattened_items.append((key, item))
            else:
                flattened_items.append((key, value))
        return urlencode(flattened_items, doseq=True)

    @staticmethod
    def _validate_create_payload(body: SavedSearchCreateRequest) -> None:
        if not body.name or not body.name.strip():
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_SAVED_SEARCH_NAME,
            )
        if not isinstance(body.search_criteria, dict) or not body.search_criteria:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_SEARCH_CRITERIA,
            )

    @staticmethod
    def _to_response(saved_search: UserSavedSearch) -> SavedSearchResponse:
        return SavedSearchResponse(
            id=saved_search.id,
            name=saved_search.name,
            search_criteria=saved_search.search_criteria,
            query_string=SavedSearchService._build_query_string(saved_search.search_criteria),
            notification_enabled=saved_search.notification_enabled,
            last_run_at=saved_search.last_run_at,
        )

    def create_saved_search(
        self, *, user: User, body: SavedSearchCreateRequest
    ) -> SavedSearchResponse:
        self._validate_create_payload(body)
        saved_search = UserSavedSearch(
            user_id=user.id,
            name=body.name.strip(),
            search_criteria=body.search_criteria,
            notification_enabled=body.notification_enabled,
        )
        try:
            self._repo.create_saved_search(saved_search)
            self._repo.commit()
            self._repo.refresh(saved_search)
            return self._to_response(saved_search)
        except IntegrityError:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.SAVED_SEARCH_NAME_EXISTS,
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

    def create_saved_searches_bulk(
        self, *, user: User, items: List[SavedSearchCreateRequest]
    ) -> List[SavedSearchResponse]:
        if not items:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_SEARCH_CRITERIA,
            )

        for body in items:
            self._validate_create_payload(body)

        normalized_names = [body.name.strip() for body in items]
        if len(set(normalized_names)) != len(normalized_names):
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.SAVED_SEARCH_NAME_EXISTS,
            )

        existing_names = self._repo.list_saved_search_names_for_user(user_id=user.id)
        if any(name in existing_names for name in normalized_names):
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.SAVED_SEARCH_NAME_EXISTS,
            )

        saved_searches = [
            UserSavedSearch(
                user_id=user.id,
                name=body.name.strip(),
                search_criteria=body.search_criteria,
                notification_enabled=body.notification_enabled,
            )
            for body in items
        ]

        try:
            for saved_search in saved_searches:
                self._repo.create_saved_search(saved_search)
            self._repo.commit()
            for saved_search in saved_searches:
                self._repo.refresh(saved_search)
            return [self._to_response(saved_search) for saved_search in saved_searches]
        except IntegrityError:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.SAVED_SEARCH_NAME_EXISTS,
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

    def list_saved_searches(self, *, user: User) -> List[SavedSearchResponse]:
        items = self._repo.list_saved_searches_for_user(user_id=user.id)
        return [self._to_response(item) for item in items]

    def get_saved_search(self, *, user: User, saved_search_id: uuid.UUID) -> SavedSearchResponse:
        saved_search = self._repo.get_saved_search_by_id_for_user(
            saved_search_id=saved_search_id,
            user_id=user.id,
        )
        if not saved_search:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.SAVED_SEARCH_NOT_FOUND,
            )
        return self._to_response(saved_search)

    def update_saved_search(
        self,
        *,
        user: User,
        saved_search_id: uuid.UUID,
        body: SavedSearchUpdateRequest,
    ) -> SavedSearchResponse:
        saved_search = self._repo.get_saved_search_by_id_for_user(
            saved_search_id=saved_search_id,
            user_id=user.id,
        )
        if not saved_search:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.SAVED_SEARCH_NOT_FOUND,
            )

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.VALIDATION_ERROR,
            )

        if "name" in updates:
            name = (updates["name"] or "").strip()
            if not name:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_SAVED_SEARCH_NAME,
                )
            existing = self._repo.get_saved_search_by_name_for_user(
                user_id=user.id, name=name
            )
            if existing and existing.id != saved_search.id:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ErrorMessages.SAVED_SEARCH_NAME_EXISTS,
                )
            saved_search.name = name

        if "search_criteria" in updates:
            criteria = updates["search_criteria"]
            if not isinstance(criteria, dict) or not criteria:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.INVALID_SEARCH_CRITERIA,
                )
            saved_search.search_criteria = criteria

        if "notification_enabled" in updates:
            saved_search.notification_enabled = bool(updates["notification_enabled"])

        try:
            self._repo.commit()
            self._repo.refresh(saved_search)
            return self._to_response(saved_search)
        except IntegrityError:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.SAVED_SEARCH_NAME_EXISTS,
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

    def delete_saved_search(self, *, user: User, saved_search_id: uuid.UUID) -> bool:
        saved_search = self._repo.get_saved_search_by_id_for_user(
            saved_search_id=saved_search_id,
            user_id=user.id,
        )
        if not saved_search:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.SAVED_SEARCH_NOT_FOUND,
            )
        try:
            self._repo.delete_saved_search(saved_search)
            self._repo.commit()
            return True
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REQUEST_FAILED,
            )

    def execute_saved_search(
        self, *, user: User, saved_search_id: uuid.UUID
    ) -> SavedSearchExecutionResponse:
        saved_search = self._repo.get_saved_search_by_id_for_user(
            saved_search_id=saved_search_id,
            user_id=user.id,
        )
        if not saved_search:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.SAVED_SEARCH_NOT_FOUND,
            )

        results = self._repo.run_saved_search_query(criteria=saved_search.search_criteria)
        try:
            self._repo.touch_last_run(saved_search)
            self._repo.commit()
        except Exception:
            self._repo.rollback()

        items = [PropertySearchResultExtended.from_orm_obj(item) for item in results]
        if self._media_url_signer is not None:
            for row in items:
                self._media_url_signer.sign_search_result_extended(row)
        return SavedSearchExecutionResponse(items=items, total=len(items))

