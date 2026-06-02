"""API endpoints for feature / amenity taxonomy."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.features import get_feature_service
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.feature import (
    FeatureCreate,
    FeatureListFilters,
    FeatureListResponse,
    FeatureResponse,
    FeatureUpdate,
)
from app.services.feature_service import FeatureService
from app.utils.constants import UserRoles
from app.utils.responses import StandardResponse

router = APIRouter()


@router.get("")
def list_features(
    service: Annotated[FeatureService, Depends(get_feature_service)],
    category_id: Optional[int] = Query(default=None),
    property_type_id: Optional[int] = Query(default=None),
    feature_group: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=True),
    include_legacy: bool = Query(default=True),
) -> StandardResponse[FeatureListResponse]:
    """List features with optional taxonomy filters."""
    filters = FeatureListFilters(
        category_id=category_id,
        property_type_id=property_type_id,
        feature_group=feature_group,
        is_active=is_active,
        include_legacy=include_legacy,
    )
    return service.list_features(filters)


@router.get("/{feature_id}")
def get_feature(
    feature_id: int,
    service: Annotated[FeatureService, Depends(get_feature_service)],
) -> StandardResponse[FeatureResponse]:
    """Return a single feature by id."""
    return service.get_feature(feature_id)


@router.post("")
def create_feature(
    payload: FeatureCreate,
    service: Annotated[FeatureService, Depends(get_feature_service)],
    _admin: Annotated[User, require_role(UserRoles.ADMIN)],
) -> StandardResponse[FeatureResponse]:
    """Create a taxonomy feature or amenity (admin)."""
    return service.create_feature(payload)


@router.patch("/{feature_id}")
def update_feature(
    feature_id: int,
    payload: FeatureUpdate,
    service: Annotated[FeatureService, Depends(get_feature_service)],
    _admin: Annotated[User, require_role(UserRoles.ADMIN)],
) -> StandardResponse[FeatureResponse]:
    """Update a taxonomy feature or amenity (admin)."""
    return service.update_feature(feature_id, payload)
