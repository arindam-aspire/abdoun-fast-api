"""Service layer for feature / amenity taxonomy."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

from app.models.property_normalized import Feature
from app.repositories.feature_repository import FeatureRepository
from app.schemas.feature import (
    FeatureCreate,
    FeatureListFilters,
    FeatureListResponse,
    FeatureResponse,
    FeatureUpdate,
)
from app.utils.constants import ErrorMessages, FeatureGroup
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus


def _slugify(value: str) -> str:
    slug = value.lower().strip()
    slug = slug.replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


class FeatureService:
    """Business logic for feature taxonomy CRUD and listing."""

    def __init__(self, repository: FeatureRepository) -> None:
        self._repo = repository

    def list_features(self, filters: FeatureListFilters) -> StandardResponse[FeatureListResponse]:
        items = self._repo.list_features(
            category_id=filters.category_id,
            property_type_id=filters.property_type_id,
            feature_group=filters.feature_group,
            is_active=filters.is_active,
            include_legacy=filters.include_legacy,
        )
        responses = [FeatureResponse.model_validate(item) for item in items]
        payload = FeatureListResponse(items=responses, total=len(responses))
        return create_success_response(data=payload, message=None)

    def get_feature(self, feature_id: int) -> StandardResponse[FeatureResponse]:
        feature = self._repo.get_by_id(feature_id)
        if feature is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.FEATURE_NOT_FOUND,
            )
        return create_success_response(
            data=FeatureResponse.model_validate(feature),
            message=None,
        )

    def create_feature(self, payload: FeatureCreate) -> StandardResponse[FeatureResponse]:
        self._validate_taxonomy_rules(
            feature_group=payload.feature_group,
            category_id=payload.category_id,
            property_type_id=payload.property_type_id,
        )
        self._ensure_category_and_type(payload.category_id, payload.property_type_id)
        if self._repo.duplicate_name_exists(
            name=payload.name.strip(),
            category_id=payload.category_id,
            property_type_id=payload.property_type_id,
            feature_group=payload.feature_group,
        ):
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.FEATURE_DUPLICATE_NAME,
            )

        slug = self._resolve_slug(
            name=payload.name,
            slug=payload.slug,
            category_id=payload.category_id,
            property_type_id=payload.property_type_id,
            feature_group=payload.feature_group,
        )
        feature = Feature(
            name=payload.name.strip(),
            slug=slug,
            category_id=payload.category_id,
            property_type_id=payload.property_type_id,
            feature_group=payload.feature_group,
            display_order=payload.display_order,
            is_active=payload.is_active,
        )
        self._repo.add(feature)
        self._repo.commit()
        created = self._repo.get_by_id(feature.id)
        return create_success_response(
            data=FeatureResponse.model_validate(created),
            message=None,
        )

    def update_feature(
        self, feature_id: int, payload: FeatureUpdate
    ) -> StandardResponse[FeatureResponse]:
        feature = self._repo.get_by_id(feature_id)
        if feature is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.FEATURE_NOT_FOUND,
            )

        fields_set = payload.model_fields_set
        category_id = payload.category_id if "category_id" in fields_set else feature.category_id
        property_type_id = (
            payload.property_type_id if "property_type_id" in fields_set else feature.property_type_id
        )
        feature_group = payload.feature_group if "feature_group" in fields_set else feature.feature_group

        if feature_group == FeatureGroup.AMENITY:
            property_type_id = None

        self._validate_taxonomy_rules(
            feature_group=feature_group,
            category_id=category_id,
            property_type_id=property_type_id,
        )
        if category_id is not None:
            self._ensure_category_and_type(category_id, property_type_id)

        new_name = payload.name.strip() if payload.name is not None else feature.name
        if category_id is not None and self._repo.duplicate_name_exists(
            name=new_name,
            category_id=category_id,
            property_type_id=property_type_id,
            feature_group=feature_group,
            exclude_id=feature.id,
        ):
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.FEATURE_DUPLICATE_NAME,
            )

        if payload.name is not None:
            feature.name = new_name
        if payload.slug is not None:
            feature.slug = self._resolve_slug(
                name=new_name,
                slug=payload.slug,
                category_id=category_id,
                property_type_id=property_type_id,
                feature_group=feature_group,
                exclude_id=feature.id,
            )
        if "category_id" in fields_set:
            feature.category_id = category_id
        feature.property_type_id = property_type_id
        if "feature_group" in fields_set:
            feature.feature_group = feature_group
        if payload.display_order is not None:
            feature.display_order = payload.display_order
        if payload.is_active is not None:
            feature.is_active = payload.is_active

        self._repo.commit()
        updated = self._repo.get_by_id(feature.id)
        return create_success_response(
            data=FeatureResponse.model_validate(updated),
            message=None,
        )

    def _validate_taxonomy_rules(
        self,
        *,
        feature_group: str,
        category_id: Optional[int],
        property_type_id: Optional[int],
    ) -> None:
        if feature_group not in FeatureGroup.ALLOWED:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.FEATURE_GROUP_INVALID,
            )
        if feature_group == FeatureGroup.AMENITY:
            if category_id is None or property_type_id is not None:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.FEATURE_AMENITY_REQUIRES_CATEGORY,
                )
            return
        if category_id is None or property_type_id is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.FEATURE_REQUIRES_CATEGORY_AND_TYPE,
            )

    def _ensure_category_and_type(
        self, category_id: int, property_type_id: Optional[int]
    ) -> None:
        category = self._repo.get_category(category_id)
        if category is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.FEATURE_CATEGORY_NOT_FOUND,
            )
        if property_type_id is None:
            return
        prop_type = self._repo.get_property_type(property_type_id)
        if prop_type is None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.FEATURE_PROPERTY_TYPE_NOT_FOUND,
            )
        if prop_type.category_id != category_id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.FEATURE_TYPE_CATEGORY_MISMATCH,
            )

    def _resolve_slug(
        self,
        *,
        name: str,
        slug: Optional[str],
        category_id: Optional[int],
        property_type_id: Optional[int],
        feature_group: str,
        exclude_id: Optional[int] = None,
    ) -> str:
        base = _slugify(slug or name)
        suffix_parts = [feature_group.lower()]
        if category_id is not None:
            suffix_parts.append(str(category_id))
        if property_type_id is not None:
            suffix_parts.append(str(property_type_id))
        candidate = base if not suffix_parts else f"{base}-{'-'.join(suffix_parts)}"
        if not self._repo.slug_exists(candidate, exclude_id=exclude_id):
            return candidate

        counter = 2
        while self._repo.slug_exists(f"{candidate}-{counter}", exclude_id=exclude_id):
            counter += 1
        return f"{candidate}-{counter}"
