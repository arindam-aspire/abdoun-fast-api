"""Storage path helpers for original/watermarked property images."""

import uuid

from app.utils.storage_paths import draft_image_original_key, draft_image_watermarked_key


def test_draft_image_original_and_watermarked_keys() -> None:
    path_id = uuid.uuid4()
    assert draft_image_original_key(path_id, "a.jpg").endswith(
        f"drafts/property-submissions/{path_id}/images/original/a.jpg"
    )
    assert draft_image_watermarked_key(path_id, "a.jpg").endswith(
        f"drafts/property-submissions/{path_id}/images/watermarked/a.jpg"
    )
