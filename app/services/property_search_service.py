"""Property search and detail service: search by params, get detail/similar by id; uses PropertyRepository."""
import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.property_repository import PropertyRepository
from app.schemas.property import (
    PropertyDetail,
    PropertySearchParams,  # type: ignore[attr-defined]
    PropertySearchResponse,
    PropertySearchResultExtended,
)
from app.utils.constants import ErrorMessages
from app.utils.status_codes import STATUS_NOT_FOUND


class PropertySearchService:
    """Service encapsulating property search and lookup behaviour."""

    def __init__(self, db: Session) -> None:
        """Store DB session and property repository for all operations.

        Args:
            db: SQLAlchemy Session (request-scoped).
        """
        self._db = db
        self._repo = PropertyRepository(db)

    def search(self, params: PropertySearchParams) -> PropertySearchResponse:
        """Search properties with filters and pagination; returns extended list response."""
        filters = self._repo.build_property_filters(
            status=params.status,
            category=params.category,
            type_slug=params.type_slug,
            city=params.city,
            locations=params.locations,
            exclusive=params.exclusive,
            budget_min=params.budget_min,
            budget_max=params.budget_max,
            min_price=params.min_price,
            max_price=params.max_price,
        )

        requires_joins = bool(
            params.category or params.type_slug or params.city or params.locations
        )
        properties, total = self._repo.search_properties(
            filters=filters,
            page=params.page,
            page_size=params.page_size,
            requires_joins=requires_joins,
        )
        owner_map = {}
        try:
            property_ids = [p.id for p in properties if isinstance(getattr(p, "id", None), uuid.UUID)]
            owner_map = self._repo.get_owner_details_by_property_ids(property_ids)
        except Exception:
            # Owner mapping must not break property listing endpoint.
            owner_map = {}

        data: List[PropertySearchResultExtended] = [
            PropertySearchResultExtended.from_orm_obj(
                p,
                lang=params.lang,
                owner_details=owner_map.get(getattr(p, "id", None), []),
            )
            for p in properties
        ]
        return PropertySearchResponse(
            data=data, total=total, page=params.page, pageSize=params.page_size
        )

    def _resolve_property_identifier(
        self,
        property_id: str,
        *,
        for_detail: bool,
    ):
        """Resolve property_id (UUID or hash) to Property or None."""
        try:
            property_uuid = uuid.UUID(property_id)
        except (ValueError, TypeError):
            try:
                target_hash = int(property_id)
            except (ValueError, TypeError):
                return None
            property_uuid = self._repo.find_property_uuid_by_hash(target_hash)
            if not property_uuid:
                return None

        if for_detail:
            return self._repo.get_property_detail(property_uuid=property_uuid)

        # Similar lookup uses a lighter option set; reuse get_property_detail for simplicity
        return self._repo.get_property_detail(property_uuid=property_uuid)

    def get_similar(
        self,
        property_id: str,
        *,
        limit: int,
        lang: Optional[str],
    ) -> PropertySearchResponse:
        source = self._resolve_property_identifier(property_id, for_detail=False)
        if not source:
            raise HTTPException(
                status_code=STATUS_NOT_FOUND,
                detail=ErrorMessages.PROPERTY_NOT_FOUND,
            )
        results = self._repo.get_similar_properties(source_property=source, limit=limit)
        data: List[PropertySearchResultExtended] = [
            PropertySearchResultExtended.from_orm_obj(p, lang=lang) for p in results
        ]
        return PropertySearchResponse(
            data=data,
            total=len(data),
            page=1,
            pageSize=len(data),
        )

    def get_detail(
        self,
        property_id: str,
        *,
        lang: Optional[str],
    ) -> PropertyDetail:
        """Return full property detail for the given property_id; 404 if not found."""
        prop = self._resolve_property_identifier(property_id, for_detail=True)
        if not prop:
            raise HTTPException(
                status_code=STATUS_NOT_FOUND,
                detail=ErrorMessages.PROPERTY_NOT_FOUND,
            )
        return PropertyDetail.from_orm_obj(prop, lang=lang)

