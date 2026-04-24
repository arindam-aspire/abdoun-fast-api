"""Unit tests for storage path helper utilities."""

import uuid

from app.utils.storage_paths import (
    draft_document_key,
    draft_image_key,
    draft_owner_document_key,
    draft_video_key,
    draft_submission_documents_prefix,
    draft_submission_images_prefix,
    draft_submission_owners_prefix,
    draft_submission_videos_prefix,
    owner_documents_prefix,
    owner_document_key,
    property_document_key,
    property_image_key,
    property_video_key,
    property_documents_prefix,
    property_images_prefix,
    property_videos_prefix,
    sanitize_filename,
)


def test_draft_submission_prefixes() -> None:
    submission_id = uuid.uuid4()
    assert draft_submission_images_prefix(submission_id).endswith(f"{submission_id}/images/")
    assert draft_submission_videos_prefix(submission_id).endswith(f"{submission_id}/videos/")
    assert draft_submission_documents_prefix(submission_id).endswith(f"{submission_id}/documents/")
    assert draft_submission_owners_prefix(submission_id).endswith(f"{submission_id}/owners/")


def test_final_property_and_owner_prefixes() -> None:
    property_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    assert property_images_prefix(property_id) == f"properties/media/{property_id}/images/"
    assert property_videos_prefix(property_id) == f"properties/media/{property_id}/videos/"
    assert property_documents_prefix(property_id) == f"properties/documents/property/{property_id}/"
    assert owner_documents_prefix(owner_id, property_id) == f"properties/documents/owner/{owner_id}/{property_id}/"


def test_storage_object_key_helpers_and_filename_sanitizing() -> None:
    submission_id = uuid.uuid4()
    property_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    dirty_name = "../my folder/front view (1).jpg"

    assert sanitize_filename(dirty_name) == "front_view_1_.jpg"
    assert draft_image_key(submission_id, dirty_name).startswith(f"drafts/property-submissions/{submission_id}/images/")
    assert draft_video_key(submission_id, "walkthrough.mp4").endswith("/videos/walkthrough.mp4")
    assert draft_document_key(submission_id, "docs/deed.pdf").endswith("/documents/deed.pdf")
    assert draft_owner_document_key(submission_id, "owners/passport.pdf").endswith("/owners/passport.pdf")

    assert property_image_key(property_id, "a.jpg").endswith(f"properties/media/{property_id}/images/a.jpg")
    assert property_video_key(property_id, "b.mp4").endswith(f"properties/media/{property_id}/videos/b.mp4")
    assert property_document_key(property_id, "c.pdf").endswith(f"properties/documents/property/{property_id}/c.pdf")
    assert owner_document_key(owner_id, property_id, "d.pdf").endswith(
        f"properties/documents/owner/{owner_id}/{property_id}/d.pdf"
    )
