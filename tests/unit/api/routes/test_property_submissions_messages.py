"""Success message selection for property submission routes."""

from __future__ import annotations

from app.api.v1.routes.property_submissions import _patch_success_message
from app.schemas.property_submission import PropertySubmissionPatchRequest
from app.utils.constants import SuccessMessages


def test_patch_success_message_full_payload_save_draft() -> None:
    body = PropertySubmissionPatchRequest(
        action="save_draft",
        payload={"basic_information": {}},
        current_step=1,
    )
    assert _patch_success_message(body) == SuccessMessages.PROPERTY_SUBMISSION_SAVED


def test_patch_success_message_single_step_save_draft() -> None:
    body = PropertySubmissionPatchRequest(
        step="basic_information",
        action="save_draft",
        data={"title": "Villa"},
    )
    assert _patch_success_message(body) == SuccessMessages.PROPERTY_SUBMISSION_SAVED


def test_patch_success_message_step_update() -> None:
    body = PropertySubmissionPatchRequest(
        step="location",
        action="save",
        data={"city": "Amman"},
    )
    assert _patch_success_message(body) == SuccessMessages.PROPERTY_SUBMISSION_UPDATED


def test_patch_success_message_step_next() -> None:
    body = PropertySubmissionPatchRequest(
        step="pricing",
        action="next",
        data={"price": 100000},
    )
    assert _patch_success_message(body) == SuccessMessages.PROPERTY_SUBMISSION_UPDATED
