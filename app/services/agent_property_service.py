"""List normalized properties created by the authenticated user (agent dashboard)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.property_listing_submission import PropertyListingSubmission
from app.models.user import User
from app.repositories.property_repository import PropertyRepository
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.schemas.agent_properties import (
    AgentDraftSubmissionItem,
    AgentPropertyListItem,
    AgentPropertyListResponse,
)


def _draft_title_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    basic = payload.get("basic_information") or {}
    title = basic.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


class AgentPropertyService:
    """Read-side service for creator-scoped property rows and related submission state."""

    def __init__(
        self,
        *,
        property_repository: PropertyRepository,
        submission_repository: PropertySubmissionRepository,
    ) -> None:
        self._properties = property_repository
        self._submissions = submission_repository

    def list_my_properties(self, *, user: User, page: int, limit: int) -> AgentPropertyListResponse:
        rows, total = self._properties.list_properties_created_by(user_id=user.id, page=page, page_size=limit)
        property_ids = [p.id for p in rows]
        submission_by_property = self._submissions.list_submissions_linked_to_properties(
            user_id=user.id,
            property_ids=property_ids,
        )

        items: list[AgentPropertyListItem] = []
        for p in rows:
            type_obj = getattr(p, "type", None)
            cat_obj = getattr(p, "category", None)
            status_obj = getattr(p, "property_status", None)
            price_val = p.price if p.price is not None else Decimal("0")
            sub: PropertyListingSubmission | None = submission_by_property.get(p.id)
            items.append(
                AgentPropertyListItem(
                    property_id=p.id,
                    property_hash=int(p.property_hash),
                    title=p.title or "",
                    listing_purpose=p.listing_purpose,
                    type_name=getattr(type_obj, "name", None),
                    type_slug=getattr(type_obj, "slug", None),
                    category_name=getattr(cat_obj, "name", None),
                    category_slug=getattr(cat_obj, "slug", None),
                    status_name=getattr(status_obj, "name", None),
                    status_slug=getattr(status_obj, "slug", None),
                    price=price_val,
                    currency=p.currency,
                    reference_number=p.reference_number,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    submission_id=sub.id if sub else None,
                    submission_status=sub.status if sub else None,
                    submission_submitted_at=sub.submitted_at if sub else None,
                    submission_reviewed_at=sub.reviewed_at if sub else None,
                    submission_review_reason=sub.review_reason if sub else None,
                )
            )

        draft_rows, draft_total = self._submissions.list_draft_submissions_without_property(
            user_id=user.id,
            limit=200,
        )
        draft_items = [
            AgentDraftSubmissionItem(
                submission_id=d.id,
                status=d.status,
                current_step=d.current_step,
                last_completed_step=d.last_completed_step,
                title=_draft_title_from_payload(d.payload if isinstance(d.payload, dict) else None),
                updated_at=d.updated_at,
            )
            for d in draft_rows
        ]

        return AgentPropertyListResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            draft_submissions=draft_items,
            draft_submissions_total=draft_total,
        )
