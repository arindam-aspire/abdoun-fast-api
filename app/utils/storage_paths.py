"""Helpers for consistent draft and final storage object key paths."""

import uuid
import re


_FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    """Return a filesystem and object-key safe filename."""
    base_name = (filename or "").strip().split("/")[-1].split("\\")[-1]
    cleaned = _FILENAME_SANITIZE_RE.sub("_", base_name).strip("._")
    return cleaned or "file"


def draft_submission_images_prefix(submission_id: uuid.UUID) -> str:
    """Draft prefix for submission image uploads."""
    return f"drafts/property-submissions/{submission_id}/images/"


def draft_submission_videos_prefix(submission_id: uuid.UUID) -> str:
    """Draft prefix for submission video uploads."""
    return f"drafts/property-submissions/{submission_id}/videos/"


def draft_submission_documents_prefix(submission_id: uuid.UUID) -> str:
    """Draft prefix for submission-level document uploads."""
    return f"drafts/property-submissions/{submission_id}/documents/"


def draft_submission_owners_prefix(submission_id: uuid.UUID) -> str:
    """Draft prefix for owner documents before owner/property ids exist."""
    return f"drafts/property-submissions/{submission_id}/owners/"


def draft_image_key(submission_id: uuid.UUID, filename: str) -> str:
    """Draft object key for property image."""
    return f"{draft_submission_images_prefix(submission_id)}{sanitize_filename(filename)}"


def draft_video_key(submission_id: uuid.UUID, filename: str) -> str:
    """Draft object key for property video."""
    return f"{draft_submission_videos_prefix(submission_id)}{sanitize_filename(filename)}"


def draft_document_key(submission_id: uuid.UUID, filename: str) -> str:
    """Draft object key for property-level document."""
    return f"{draft_submission_documents_prefix(submission_id)}{sanitize_filename(filename)}"


def draft_owner_document_key(submission_id: uuid.UUID, filename: str) -> str:
    """Draft object key for owner document."""
    return f"{draft_submission_owners_prefix(submission_id)}{sanitize_filename(filename)}"


def property_images_prefix(property_id: uuid.UUID) -> str:
    """Final prefix for property images."""
    return f"properties/media/{property_id}/images/"


def property_videos_prefix(property_id: uuid.UUID) -> str:
    """Final prefix for property videos."""
    return f"properties/media/{property_id}/videos/"


def property_documents_prefix(property_id: uuid.UUID) -> str:
    """Final prefix for property-level documents."""
    return f"properties/documents/property/{property_id}/"


def owner_documents_prefix(owner_id: uuid.UUID, property_id: uuid.UUID) -> str:
    """Final prefix for owner-specific documents under a property."""
    return f"properties/documents/owner/{owner_id}/{property_id}/"


def property_image_key(property_id: uuid.UUID, filename: str) -> str:
    """Final object key for property image."""
    return f"{property_images_prefix(property_id)}{sanitize_filename(filename)}"


def property_video_key(property_id: uuid.UUID, filename: str) -> str:
    """Final object key for property video."""
    return f"{property_videos_prefix(property_id)}{sanitize_filename(filename)}"


def property_document_key(property_id: uuid.UUID, filename: str) -> str:
    """Final object key for property-level document."""
    return f"{property_documents_prefix(property_id)}{sanitize_filename(filename)}"


def owner_document_key(owner_id: uuid.UUID, property_id: uuid.UUID, filename: str) -> str:
    """Final object key for owner document."""
    return f"{owner_documents_prefix(owner_id, property_id)}{sanitize_filename(filename)}"


def user_profile_picture_prefix(user_id: uuid.UUID) -> str:
    """Prefix for authenticated user's profile picture uploads."""
    return f"users/profile/{user_id}/profile_pic/"


def user_profile_picture_key(user_id: uuid.UUID, filename: str) -> str:
    """Object key for a user's profile picture (S3 path under users/profile/...)."""
    return f"{user_profile_picture_prefix(user_id)}{sanitize_filename(filename)}"
