"""Repository for feature / amenity taxonomy."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.property_normalized import (
    CategoryFeature,
    Feature,
    PropertyCategory,
    PropertyType,
    TypeFeature,
)


class FeatureRepository:
    """Data access for features with taxonomy filters."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, feature_id: int) -> Optional[Feature]:
        stmt = (
            select(Feature)
            .options(
                joinedload(Feature.category),
                joinedload(Feature.property_type),
            )
            .where(Feature.id == feature_id)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_category(self, category_id: int) -> Optional[PropertyCategory]:
        return self._db.get(PropertyCategory, category_id)

    def get_property_type(self, property_type_id: int) -> Optional[PropertyType]:
        return self._db.get(PropertyType, property_type_id)

    def list_features(
        self,
        *,
        category_id: Optional[int],
        property_type_id: Optional[int],
        feature_group: Optional[str],
        is_active: Optional[bool],
        include_legacy: bool,
    ) -> List[Feature]:
        stmt: Select = select(Feature).options(
            joinedload(Feature.category),
            joinedload(Feature.property_type),
        )

        if is_active is not None:
            stmt = stmt.where(Feature.is_active.is_(is_active))

        taxonomy_clause = self._build_taxonomy_filter(
            category_id=category_id,
            property_type_id=property_type_id,
            feature_group=feature_group,
            include_legacy=include_legacy,
        )
        if taxonomy_clause is not None:
            stmt = stmt.where(taxonomy_clause)

        stmt = stmt.order_by(
            Feature.display_order,
            Feature.name,
        )
        return list(self._db.execute(stmt).unique().scalars().all())

    def _build_taxonomy_filter(
        self,
        *,
        category_id: Optional[int],
        property_type_id: Optional[int],
        feature_group: Optional[str],
        include_legacy: bool,
    ):
        if category_id is None and property_type_id is None and feature_group is None:
            return None

        direct_clauses = []
        if feature_group is not None:
            direct_clauses.append(Feature.feature_group == feature_group)
        if category_id is not None:
            direct_clauses.append(Feature.category_id == category_id)
        if property_type_id is not None:
            direct_clauses.append(Feature.property_type_id == property_type_id)
        if feature_group == "AMENITY":
            direct_clauses.append(Feature.property_type_id.is_(None))

        direct_match = and_(*direct_clauses) if direct_clauses else None

        if not include_legacy or category_id is None:
            return direct_match

        legacy_clauses = []
        if feature_group in (None, "AMENITY"):
            legacy_amenity = Feature.id.in_(
                select(CategoryFeature.feature_id).where(
                    CategoryFeature.category_id == category_id
                )
            )
            legacy_clauses.append(legacy_amenity)
        if feature_group in (None, "FEATURE") and property_type_id is not None:
            legacy_feature = Feature.id.in_(
                select(TypeFeature.feature_id).where(
                    TypeFeature.property_type_id == property_type_id
                )
            )
            legacy_clauses.append(legacy_feature)

        if not legacy_clauses:
            return direct_match

        legacy_match = or_(*legacy_clauses)
        if direct_match is None:
            return legacy_match
        return or_(direct_match, legacy_match)

    def duplicate_name_exists(
        self,
        *,
        name: str,
        category_id: int,
        property_type_id: Optional[int],
        feature_group: str,
        exclude_id: Optional[int] = None,
    ) -> bool:
        stmt = select(Feature.id).where(
            Feature.name == name,
            Feature.category_id == category_id,
            Feature.feature_group == feature_group,
        )
        if feature_group == "AMENITY":
            stmt = stmt.where(Feature.property_type_id.is_(None))
        else:
            stmt = stmt.where(Feature.property_type_id == property_type_id)

        if exclude_id is not None:
            stmt = stmt.where(Feature.id != exclude_id)

        return self._db.execute(stmt).first() is not None

    def slug_exists(self, slug: str, *, exclude_id: Optional[int] = None) -> bool:
        stmt = select(Feature.id).where(Feature.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(Feature.id != exclude_id)
        return self._db.execute(stmt).first() is not None

    def add(self, feature: Feature) -> Feature:
        self._db.add(feature)
        self._db.flush()
        return feature

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, feature: Feature) -> None:
        self._db.refresh(feature)

    def rollback(self) -> None:
        self._db.rollback()
