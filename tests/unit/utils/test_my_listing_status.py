"""Unit tests for my-listings status normalization."""

from app.utils.my_listing_status import normalize_my_listing_status


def test_normalize_pending_from_submission() -> None:
    assert normalize_my_listing_status(catalog_status_slug="verified", submission_status="submitted") == "Pending"


def test_normalize_draft_from_submission() -> None:
    assert normalize_my_listing_status(catalog_status_slug="active", submission_status="in_progress") == "Draft"


def test_normalize_active_from_catalog() -> None:
    assert normalize_my_listing_status(catalog_status_slug="verified", submission_status=None) == "Active"


def test_normalize_rejected() -> None:
    assert normalize_my_listing_status(catalog_status_slug="pending", submission_status="rejected") == "Rejected"


def test_normalize_inactive() -> None:
    assert normalize_my_listing_status(catalog_status_slug="sold", submission_status=None) == "Inactive"
