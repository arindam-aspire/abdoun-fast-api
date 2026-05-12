"""Business logic for user saved searches."""
import uuid
from urllib.parse import urlencode
from typing import List

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.constants.notification_types import NotificationType
from app.domains.shared.pagination import calculate_pagination
from app.models.user import User
from app.models.user_saved_search import UserSavedSearch
from app.repositories.saved_search_repository import SavedSearchRepository
from app.schemas.property import PropertySearchResultExtended
from app.schemas.saved_search import (
    SavedSearchCreateRequest,
    SavedSearchExecutionResponse,
    SavedSearchListResponse,
    SavedSearchResponse,
    SavedSearchUpdateRequest,
)
from app.services.media_url_signer import MediaUrlSigner
from app.services.notification_event_emitter import NotificationEmitPayload, NotificationEventEmitter
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.logger import api_logger
from app.utils.log_messages import format_log_message
from app.utils.status_codes import HTTPStatus


class SavedSearchService:
    """Service layer for saved-search CRUD and execution."""

    def __init__(
        self,
        repository: SavedSearchRepository,
        *,
        media_url_signer: MediaUrlSigner | None = None,
        notification_emitter: NotificationEventEmitter | None = None,
    ) -> None:
        self._repo = repository
        self._media_url_signer = media_url_signer
        self._notification_emitter = notification_emitter

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

    def _notify_saved_search_created(self, *, user: User, saved_search: UserSavedSearch) -> None:
        """Notify the creating user only (idempotent per saved search)."""
        if self._notification_emitter is None:
            return

        search_name = (getattr(saved_search, "name", None) or "").strip() or "Saved search"
        creator_raw = getattr(user, "full_name", None)
        creator_name = str(creator_raw).strip() if creator_raw is not None else ""
        if not creator_name:
            creator_name = "Unknown"

        role_names = {getattr(r, "name", None) for r in (getattr(user, "roles", None) or [])}
        role_names.discard(None)
        saved_id_str = str(saved_search.id)
        et = NotificationType.SAVED_SEARCH_CREATED.value
        try:
            self._notification_emitter.emit(
                payload=NotificationEmitPayload(
                    event_type=et,
                    type_key=et,
                    recipient_user_id=user.id,
                    actor_user_id=user.id,
                    recipient_role_names=frozenset(role_names),
                    template_data={
                        "search_name": search_name,
                        "creator_name": creator_name,
                        "entity_type": "saved_search",
                        "entity_id": saved_id_str,
                        "metadata": {"saved_search_id": saved_id_str},
                    },
                    idempotency_key=f"saved_search.created:{user.id}:{saved_id_str}",
                )
            )
        except Exception:
            api_logger.error(
                format_log_message(
                    "Saved search notification dispatch failed user_id={uid} saved_search_id={sid}",
                    uid=str(user.id),
                    sid=saved_id_str,
                ),
                exc_info=True,
            )

    def _notify_saved_searches_created_bulk(self, *, user: User, saved_searches: List[UserSavedSearch]) -> None:
        if self._notification_emitter is None or not saved_searches:
            return
        role_names = {getattr(r, "name", None) for r in (getattr(user, "roles", None) or [])}
        role_names.discard(None)
        fr = frozenset(role_names)
        et = NotificationType.SAVED_SEARCH_CREATED.value
        creator_raw = getattr(user, "full_name", None)
        creator_name = str(creator_raw).strip() if creator_raw is not None else ""
        if not creator_name:
            creator_name = "Unknown"
        payloads: list[NotificationEmitPayload] = []
        for saved_search in saved_searches:
            search_name = (getattr(saved_search, "name", None) or "").strip() or "Saved search"
            saved_id_str = str(saved_search.id)
            payloads.append(
                NotificationEmitPayload(
                    event_type=et,
                    type_key=et,
                    recipient_user_id=user.id,
                    actor_user_id=user.id,
                    recipient_role_names=fr,
                    template_data={
                        "search_name": search_name,
                        "creator_name": creator_name,
                        "entity_type": "saved_search",
                        "entity_id": saved_id_str,
                        "metadata": {"saved_search_id": saved_id_str},
                    },
                    idempotency_key=f"saved_search.created:{user.id}:{saved_id_str}",
                )
            )
        try:
            self._notification_emitter.emit_bulk(payloads=payloads)
        except Exception:
            api_logger.error(
                format_log_message(
                    "Saved search bulk notification dispatch failed user_id={uid} count={n}",
                    uid=str(user.id),
                    n=len(payloads),
                ),
                exc_info=True,
            )

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

        # In-app confirmation for creator only (NotificationEventEmitter uses its own commit).
        self._notify_saved_search_created(user=user, saved_search=saved_search)
        return self._to_response(saved_search)

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
            self._notify_saved_searches_created_bulk(user=user, saved_searches=saved_searches)
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

    def list_saved_searches(self, *, user: User, page: int, page_size: int) -> SavedSearchListResponse:
        items = self._repo.list_saved_searches_for_user(user_id=user.id)
        response_items = [self._to_response(item) for item in items]
        total = len(response_items)
        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        paged_items = response_items[meta.offset : meta.offset + meta.page_size]
        return SavedSearchListResponse(
            items=paged_items,
            total=total,
            page=meta.page,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
        )

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
        self, *, user: User, saved_search_id: uuid.UUID, page: int, page_size: int
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
        total = len(items)
        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        paged_items = items[meta.offset : meta.offset + meta.page_size]
        return SavedSearchExecutionResponse(
            items=paged_items,
            total=total,
            page=meta.page,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
        )

