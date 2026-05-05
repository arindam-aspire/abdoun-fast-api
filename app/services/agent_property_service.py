"""List normalized properties created by the authenticated user (agent dashboard)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domains.shared.pagination import calculate_pagination
from app.models.property_listing_submission import PropertyListingSubmission
from app.models.user import User
from app.repositories.property_repository import PropertyRepository
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.schemas.agent_properties import (
    AgentDraftSubmissionItem,
    AgentDraftSubmissionListResponse,
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


def _submission_workflow_label(submission_status: str | None) -> str | None:
    """Map stored workflow value to a stable key for the agent UI (e.g. ``verified`` when `approved`)."""
    if not submission_status:
        return None
    return {
        "draft": "draft",
        "in_progress": "draft",
        "submitted": "pending_admin_approval",
        "changes_requested": "changes_requested",
        "rejected": "rejected",
        "approved": "verified",
    }.get(submission_status, submission_status)


def _can_edit_submission(submission_status: str | None) -> bool:
    if not submission_status:
        return False
    return submission_status not in {"submitted", "approved"}


def _can_delete_submission(submission_status: str | None) -> bool:
    if not submission_status:
        return False
    return submission_status in {"rejected", "draft", "in_progress", "changes_requested"}


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

    def list_my_properties(
        self,
        *,
        user: User,
        page: int,
        page_size: int,
        include_drafts: bool = False,
        search: str | None = None,
        status: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> AgentPropertyListResponse:
        rows, total = self._properties.list_properties_for_agent(
            agent_user_id=user.id,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )
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
            wf = sub.status if sub else None
            # Backward-compatible fallback:
            # Legacy catalog properties may be assigned to an agent without ever going through the
            # submission workflow (no PropertyListingSubmission row). In that case, the agent UI
            # should still treat verified/active listings as "approved/verified" for filtering.
            if wf is None:
                status_slug = getattr(status_obj, "slug", None)
                if status_slug in {"verified", "active"}:
                    wf = "approved"
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
                    submission_status=wf,
                    submission_submitted_at=sub.submitted_at if sub else None,
                    submission_reviewed_at=sub.reviewed_at if sub else None,
                    submission_review_reason=sub.review_reason if sub else None,
                    submission_workflow_label=_submission_workflow_label(wf),
                    can_edit_submission=_can_edit_submission(wf),
                    can_delete_submission=_can_delete_submission(wf),
                )
            )

        extra: dict[str, Any] = {}
        if include_drafts:
            draft_rows, draft_total = self._submissions.list_draft_submissions_without_property(
                user_id=user.id,
                limit=200,
            )
            extra["draft_submissions"] = [
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
            extra["draft_submissions_total"] = draft_total

        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        return AgentPropertyListResponse(
            items=items,
            total=total,
            page=page,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
            **extra,
        )

    def list_my_draft_submissions(self, *, user: User, page: int, page_size: int) -> AgentDraftSubmissionListResponse:
        # Repo returns newest-first; no DB-level paging for drafts yet, so page in memory.
        rows, total = self._submissions.list_draft_submissions_without_property(user_id=user.id, limit=200)
        items = [
            AgentDraftSubmissionItem(
                submission_id=d.id,
                status=d.status,
                current_step=d.current_step,
                last_completed_step=d.last_completed_step,
                title=_draft_title_from_payload(d.payload if isinstance(d.payload, dict) else None),
                updated_at=d.updated_at,
            )
            for d in rows
        ]
        offset = max(page - 1, 0) * page_size
        paged = items[offset : offset + page_size]
        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        return AgentDraftSubmissionListResponse(
            items=paged,
            total=total,
            page=page,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
        )
