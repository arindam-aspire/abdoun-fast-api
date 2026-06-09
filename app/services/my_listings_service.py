"""Service for GET /properties/my-listings."""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.repositories.property_repository import PropertyRepository
from app.schemas.my_listings import MyListingAgentInfo, MyListingItem, MyListingsResponse
from app.utils.constants import ErrorMessages
from app.utils.my_listing_status import MY_LISTING_STATUS_FILTERS, normalize_my_listing_status
from app.utils.status_codes import HTTPStatus


class MyListingsService:
    """Role-scoped property listings for agent and admin dashboards."""

    def __init__(self, *, property_repository: PropertyRepository) -> None:
        self._repo = property_repository

    def list_my_listings(
        self,
        *,
        scope: str,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        status: str | None = None,
        property_type: str | None = None,
        search: str | None = None,
    ) -> MyListingsResponse:
        status_norm = (status or "").strip().lower()
        if status_norm and status_norm not in MY_LISTING_STATUS_FILTERS:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_MY_LISTING_STATUS_FILTER,
            )

        rows, total, submission_by_property = self._repo.list_my_listings(
            scope=scope,
            agent_user_id=user_id if scope == "agent" else None,
            page=page,
            page_size=page_size,
            status=status,
            property_type=property_type,
            search=search,
        )

        items: list[MyListingItem] = []
        for prop in rows:
            type_obj = getattr(prop, "type", None)
            status_obj = getattr(prop, "property_status", None)
            catalog_slug = getattr(status_obj, "slug", None)
            sub_status = submission_by_property.get(prop.id)
            agent_user = getattr(prop, "agent_user", None)

            agent_info: MyListingAgentInfo | None = None
            if agent_user is not None and getattr(agent_user, "id", None) is not None:
                agent_info = MyListingAgentInfo(
                    id=agent_user.id,
                    full_name=agent_user.full_name,
                    email=agent_user.email,
                    phone_number=agent_user.phone_number,
                )

            items.append(
                MyListingItem(
                    property_id=prop.id,
                    property_hash_id=int(prop.property_hash),
                    title=prop.title or "",
                    status=normalize_my_listing_status(
                        catalog_status_slug=catalog_slug,
                        submission_status=sub_status,
                    ),
                    property_type=getattr(type_obj, "slug", None),
                    created_at=prop.created_at,
                    updated_at=prop.updated_at,
                    created_by=prop.created_by,
                    agent=agent_info,
                )
            )

        return MyListingsResponse(
            items=items,
            page=page,
            page_size=page_size,
            total_count=total,
        )
