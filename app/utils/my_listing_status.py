"""Normalize catalog + submission workflow into dashboard listing status labels."""

from __future__ import annotations

MY_LISTING_STATUS_FILTERS = frozenset({"draft", "pending", "active", "rejected", "inactive"})


def normalize_my_listing_status(
    *,
    catalog_status_slug: str | None,
    submission_status: str | None = None,
) -> str:
    """Map DB slugs to UI labels: Draft, Pending, Active, Rejected, Inactive."""
    sub = (submission_status or "").strip().lower()
    slug = (catalog_status_slug or "").strip().lower()

    if sub in {"submitted"}:
        return "Pending"
    if sub in {"rejected"}:
        return "Rejected"
    if sub in {"draft", "in_progress"}:
        return "Draft"

    if slug in {"draft"}:
        return "Draft"
    if slug in {"pending"}:
        return "Pending"
    if slug in {"rejected"}:
        return "Rejected"
    if slug in {"inactive", "sold", "rented", "deal_closed"}:
        return "Inactive"
    if slug in {"active", "verified", "available"}:
        return "Active"

    if slug:
        return slug.replace("_", " ").title()
    return "Active"


def my_listing_status_sql_filter(status_norm: str, *, latest_wf, catalog_slug) -> object:
    """SQLAlchemy filter for optional ``status`` query param (allow-list only)."""
    from sqlalchemy import false, or_

    verified_slugs = ("verified", "active", "available")

    if status_norm == "draft":
        return or_(latest_wf.in_(("draft", "in_progress")), catalog_slug == "draft")
    if status_norm == "pending":
        return or_(latest_wf == "submitted", catalog_slug == "pending")
    if status_norm == "active":
        return or_(catalog_slug.in_(verified_slugs), latest_wf == "approved")
    if status_norm == "rejected":
        return or_(latest_wf == "rejected", catalog_slug == "rejected")
    if status_norm == "inactive":
        return catalog_slug.in_(("inactive", "sold", "rented", "deal_closed"))
    return false()  # unreachable when validated upstream
