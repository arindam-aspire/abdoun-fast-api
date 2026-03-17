from __future__ import annotations

import uuid
from typing import Any, List, Optional, Tuple

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.property_normalized import (
    Area,
    City,
    PropertyCategory,
    PropertyFeature,
    PropertyNormalized as Property,
    PropertyType,
)


class PropertyRepository:
    """Repository for property search and lookup operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _base_detail_query(self, options: Optional[List[Any]] = None) -> Select:
        stmt = select(Property)
        if options:
            stmt = stmt.options(*options)
        return stmt

    def load_property_with_options(
        self,
        *,
        property_uuid: uuid.UUID,
        options: List[Any],
    ) -> Optional[Property]:
        stmt = self._base_detail_query(options=options).where(Property.id == property_uuid)
        return (
            self._db.execute(stmt)
            .unique()
            .scalar_one_or_none()
        )

    def find_property_uuid_by_hash(self, target_hash: int) -> Optional[uuid.UUID]:
        from app.schemas.property import uuid_to_int_hash

        # Indexed lookup by stored hash, then verify to guard against modulo collisions.
        candidate_ids = (
            self._db.execute(
                select(Property.id).where(Property.property_hash == target_hash)
            )
            .scalars()
            .all()
        )
        for prop_id in candidate_ids:
            if isinstance(prop_id, uuid.UUID) and uuid_to_int_hash(prop_id) == target_hash:
                return prop_id
        return None

    # Search helpers (mirror existing behaviour)

    def build_property_filters(
        self,
        *,
        status: Optional[str],
        category: Optional[str],
        type_slug: Optional[str],
        city: Optional[str],
        locations: Optional[str],
        exclusive: Optional[str],
        budget_min: Optional[str],
        budget_max: Optional[str],
        min_price: Optional[str],
        max_price: Optional[str],
    ) -> List[Any]:
        filters: List[Any] = []
        status_lower = status.lower() if status else None

        self._append_status_filter(filters, status_lower)
        self._append_category_filter(filters, category)
        self._append_type_filter(filters, type_slug)
        self._append_city_filter(filters, city)
        self._append_locations_filter(filters, locations)
        self._append_exclusive_filter(filters, exclusive)

        min_budget = budget_min or min_price
        max_budget = budget_max or max_price
        self._append_budget_bound_filter(filters, min_budget, status_lower, is_min=True)
        self._append_budget_bound_filter(filters, max_budget, status_lower, is_min=False)

        return filters

    def _append_status_filter(self, filters: List[Any], status_lower: Optional[str]) -> None:
        if status_lower == "buy":
            filters.append(Property.selling_price_amount.isnot(None))
        elif status_lower == "rent":
            filters.append(Property.rent_price_amount.isnot(None))

    def _append_category_filter(self, filters: List[Any], category: Optional[str]) -> None:
        if not category:
            return

        category_lower = category.lower()
        if category_lower in ("land", "lands"):
            filters.append(func.lower(PropertyCategory.name).contains("land"))
        elif category_lower == "residential":
            filters.append(
                or_(
                    func.lower(PropertyCategory.name).contains("residential"),
                    func.lower(PropertyType.name).contains("apartment"),
                    func.lower(PropertyType.name).contains("villa"),
                    func.lower(PropertyType.name).contains("house"),
                    func.lower(PropertyType.name).contains("building"),
                    func.lower(PropertyType.name).contains("farm"),
                )
            )
        elif category_lower == "commercial":
            filters.append(
                or_(
                    func.lower(PropertyCategory.name).contains("commercial"),
                    func.lower(PropertyType.name).contains("office"),
                    func.lower(PropertyType.name).contains("showroom"),
                    func.lower(PropertyType.name).contains("warehouse"),
                    func.lower(PropertyType.name).contains("business"),
                )
            )
        else:
            filters.append(func.lower(PropertyCategory.name).contains(category_lower))

    def _append_type_filter(self, filters: List[Any], type_slug: Optional[str]) -> None:
        if not type_slug:
            return

        type_lower = type_slug.lower().replace("-", " ")
        if "apartment" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("apartment"))
        elif "villa" in type_lower:
            filters.append(
                or_(
                    func.lower(PropertyType.name).contains("villa"),
                    func.lower(PropertyType.name).contains("house"),
                )
            )
        elif "building" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("building"))
        elif "farm" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("farm"))
        elif "office" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("office"))
        elif "showroom" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("showroom"))
        elif "warehouse" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("warehouse"))
        elif "business" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("business"))
        elif "land" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("land"))
        else:
            filters.append(func.lower(PropertyType.name).contains(type_lower))

    def _append_city_filter(self, filters: List[Any], city: Optional[str]) -> None:
        if not city:
            return

        city_lower = city.lower()
        filters.append(
            or_(
                func.lower(City.name).contains(city_lower),
                func.lower(Property.location_name).contains(city_lower),
            )
        )

    def _append_locations_filter(self, filters: List[Any], locations: Optional[str]) -> None:
        if not locations:
            return

        location_list = [loc.strip().lower() for loc in locations.split(",") if loc.strip()]
        if not location_list:
            return

        location_filters = [
            or_(
                func.lower(Area.name).contains(loc),
                func.lower(Property.location_name).contains(loc),
            )
            for loc in location_list
        ]
        filters.append(or_(*location_filters))

    def _append_exclusive_filter(self, filters: List[Any], exclusive: Optional[str]) -> None:
        if exclusive is None:
            return

        exclusive_bool = str(exclusive).lower() in ("true", "1", "yes")
        filters.append(Property.is_exclusive.is_(exclusive_bool))

    def _append_budget_bound_filter(
        self,
        filters: List[Any],
        value_raw: Optional[str],
        status_lower: Optional[str],
        *,
        is_min: bool,
    ) -> None:
        if not value_raw:
            return

        try:
            value = float(value_raw)
        except (ValueError, TypeError):
            return

        if status_lower == "buy":
            condition = (
                Property.selling_price_amount >= value
                if is_min
                else Property.selling_price_amount <= value
            )
        elif status_lower == "rent":
            condition = (
                Property.rent_price_amount >= value
                if is_min
                else Property.rent_price_amount <= value
            )
        else:
            condition = or_(
                Property.selling_price_amount >= value
                if is_min
                else Property.selling_price_amount <= value,
                Property.rent_price_amount >= value
                if is_min
                else Property.rent_price_amount <= value,
            )
        filters.append(condition)

    def build_count_statement(self, filters: List[Any], requires_joins: bool) -> Select:
        stmt: Select = select(func.count(Property.id))
        if requires_joins:
            stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
            stmt = stmt.join(PropertyType, Property.type_id == PropertyType.id)
            stmt = stmt.join(City, Property.city_id == City.id)
            stmt = stmt.join(Area, Property.location_id == Area.id)
        if filters:
            stmt = stmt.where(and_(*filters))
        return stmt

    # Search queries

    def search_properties(
        self,
        *,
        filters: List[Any],
        page: int,
        page_size: int,
        requires_joins: bool,
    ) -> tuple[List[Property], int]:
        stmt: Select = select(Property).options(
            joinedload(Property.category),
            joinedload(Property.type),
            joinedload(Property.city),
            joinedload(Property.area_rel),
            joinedload(Property.property_status),
            joinedload(Property.translations),
        )

        stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
        stmt = stmt.join(PropertyType, Property.type_id == PropertyType.id)
        stmt = stmt.join(City, Property.city_id == City.id)
        stmt = stmt.join(Area, Property.location_id == Area.id)

        if filters:
            stmt = stmt.where(and_(*filters))

        count_stmt = self.build_count_statement(filters, requires_joins)
        total = self._db.execute(count_stmt).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Property.created_at.desc()).offset(offset).limit(page_size)
        results = self._db.execute(stmt).unique().scalars().all()
        return list(results), int(total)

    def get_similar_properties(
        self,
        *,
        source_property: Property,
        limit: int,
    ) -> List[Property]:
        stmt: Select = select(Property).options(
            joinedload(Property.category),
            joinedload(Property.type),
            joinedload(Property.city),
            joinedload(Property.area_rel),
            joinedload(Property.translations),
        )
        stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
        stmt = stmt.join(City, Property.city_id == City.id)

        filters: List[Any] = [Property.id != source_property.id]
        if source_property.category_id:
            filters.append(Property.category_id == source_property.category_id)
        if source_property.city_id:
            filters.append(Property.city_id == source_property.city_id)

        tolerance = 0.2
        if source_property.selling_price_amount:
            price = float(source_property.selling_price_amount)
            filters.append(
                and_(
                    Property.selling_price_amount.isnot(None),
                    Property.selling_price_amount >= price * (1 - tolerance),
                    Property.selling_price_amount <= price * (1 + tolerance),
                )
            )
        elif source_property.rent_price_amount:
            price = float(source_property.rent_price_amount)
            filters.append(
                and_(
                    Property.rent_price_amount.isnot(None),
                    Property.rent_price_amount >= price * (1 - tolerance),
                    Property.rent_price_amount <= price * (1 + tolerance),
                )
            )

        if source_property.bedrooms:
            filters.append(
                or_(
                    Property.bedrooms == source_property.bedrooms,
                    Property.bedrooms == source_property.bedrooms - 1,
                    Property.bedrooms == source_property.bedrooms + 1,
                )
            )
        if source_property.bathrooms:
            filters.append(
                or_(
                    Property.bathrooms == source_property.bathrooms,
                    Property.bathrooms == source_property.bathrooms - 1,
                    Property.bathrooms == source_property.bathrooms + 1,
                )
            )

        area_value = getattr(source_property, "area", None) or getattr(
            source_property, "built_up_area", None
        )
        if area_value:
            area = float(area_value)
            filters.append(
                and_(
                    Property.area.isnot(None),
                    Property.area >= area * (1 - tolerance),
                    Property.area <= area * (1 + tolerance),
                )
            )

        stmt = stmt.where(and_(*filters)).order_by(Property.created_at.desc()).limit(limit)
        results = self._db.execute(stmt).unique().scalars().all()
        return list(results)

    def get_property_detail(
        self,
        *,
        property_uuid: uuid.UUID,
    ) -> Optional[Property]:
        options: List[Any] = [
            joinedload(Property.category),
            joinedload(Property.type),
            joinedload(Property.city),
            joinedload(Property.area_rel),
            joinedload(Property.property_status),
            joinedload(Property.translations),
            joinedload(Property.features).joinedload(PropertyFeature.feature),
        ]
        return self.load_property_with_options(property_uuid=property_uuid, options=options)

    def geo_search(
        self,
        *,
        bounds: Optional[Tuple[float, float, float, float]] = None,
        polygon_geojson: Optional[str] = None,
        limit: int,
    ) -> List[Property]:
        """Spatial search: bounds (min_lng, min_lat, max_lng, max_lat) or polygon GeoJSON."""
        stmt: Select = select(Property).options(
            joinedload(Property.category),
            joinedload(Property.type),
            joinedload(Property.city),
            joinedload(Property.area_rel),
        )
        if bounds is not None:
            min_lng, min_lat, max_lng, max_lat = bounds
            envelope = func.ST_MakeEnvelope(
                min_lng, min_lat, max_lng, max_lat, 4326
            )
            stmt = stmt.where(func.ST_Intersects(Property.location, envelope))
        elif polygon_geojson is not None:
            geom = func.ST_GeomFromGeoJSON(polygon_geojson)
            stmt = stmt.where(func.ST_Within(Property.location, geom))
        stmt = stmt.limit(limit)
        results = self._db.execute(stmt).unique().scalars().all()
        return list(results)

