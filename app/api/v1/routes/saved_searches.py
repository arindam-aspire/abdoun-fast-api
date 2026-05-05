"""Authenticated endpoints for user saved searches."""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.saved_searches import get_saved_search_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User
from app.schemas.saved_search import (
    SavedSearchBulkCreateRequest,
    SavedSearchCreateRequest,
    SavedSearchExecutionResponse,
    SavedSearchListResponse,
    SavedSearchResponse,
    SavedSearchUpdateRequest,
)
from app.services.saved_search_service import SavedSearchService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.post("", response_model=StandardResponse[SavedSearchResponse])
def create_saved_search(
    body: SavedSearchCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
):
    """Create one saved search for the current user."""
    result = service.create_saved_search(user=current_user, body=body)
    return create_success_response(data=result, message=None)


@router.post("/bulk", response_model=StandardResponse[List[SavedSearchResponse]])
def create_saved_searches_bulk(
    body: SavedSearchBulkCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
):
    """Create multiple saved searches in one transaction."""
    result = service.create_saved_searches_bulk(user=current_user, items=body.items)
    return create_success_response(data=result, message=None)


@router.get("", response_model=StandardResponse[SavedSearchListResponse])
def list_saved_searches(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
    page: Annotated[int, Query(ge=1, description="1-based page index.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize", description="Items per page.")] = 20,
):
    """List saved searches for the current user with page-based pagination."""
    result = service.list_saved_searches(user=current_user, page=page, page_size=page_size)
    return create_success_response(data=result, message=None)


@router.get("/{id}", response_model=StandardResponse[SavedSearchResponse])
def get_saved_search(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
):
    """Get one saved search by id for the current user."""
    result = service.get_saved_search(user=current_user, saved_search_id=id)
    return create_success_response(data=result, message=None)


@router.delete("/{id}", response_model=StandardResponse[bool])
def delete_saved_search(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
):
    """Delete one saved search by id."""
    result = service.delete_saved_search(user=current_user, saved_search_id=id)
    return create_success_response(data=result, message=None)


@router.patch("/{id}", response_model=StandardResponse[SavedSearchResponse])
def update_saved_search(
    id: uuid.UUID,
    body: SavedSearchUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
):
    """Update one saved search by id."""
    result = service.update_saved_search(
        user=current_user,
        saved_search_id=id,
        body=body,
    )
    return create_success_response(data=result, message=None)


@router.get("/{id}/results", response_model=StandardResponse[SavedSearchExecutionResponse])
def execute_saved_search(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SavedSearchService, Depends(get_saved_search_service)],
    page: Annotated[int, Query(ge=1, description="1-based page index.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize", description="Items per page.")] = 20,
):
    """Execute saved-search criteria and return paginated matching active properties."""
    result = service.execute_saved_search(
        user=current_user,
        saved_search_id=id,
        page=page,
        page_size=page_size,
    )
    return create_success_response(data=result, message=None)

