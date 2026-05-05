"""Service layer for list-your-property submission workflow."""

from __future__ import annotations

import re
import uuid
import copy
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.domains.shared.pagination import calculate_pagination
from app.models.owner import Owner, PropertyOwner
from app.models.property_listing_submission import PropertyListingSubmission
from app.models.property_normalized import PropertyFeature, PropertyMedia, PropertyNormalized
from app.models.user import User
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.schemas.property_submission import (
    AdminSubmissionDetailResponse,
    AdminSubmissionListItem,
    AdminSubmissionListResponse,
    AdminSubmissionReviewRequest,
    AdminSubmissionReviewResponse,
    CreateAndSubmitPropertySubmissionRequest,
    DEFAULT_STEP_COMPLETION,
    DEFAULT_SUBMISSION_PAYLOAD,
    STEP_INDEX,
    STEP_ORDER,
    CreatePropertySubmissionRequest,
    PropertySubmissionCreateResponse,
    PropertySubmissionDetailResponse,
    PropertySubmissionDeleteResponse,
    PropertySubmissionPatchRequest,
    PropertySubmissionPatchResponse,
    PropertySubmissionSubmitRequest,
    PropertySubmissionSubmitResponse,
    SubmissionStep,
)
from app.schemas.property import uuid_to_int_hash
from app.utils.constants import ErrorMessages
from app.utils.dicts import deep_merge_dict
from app.utils.logger import service_logger
from app.utils.status_codes import HTTPStatus


class PropertySubmissionService:
    """Business logic for list-your-property drafts and submit.

    New clients keep stepper state locally until **Save as Draft** (create with ``payload``) or **Submit**
    (``create_and_submit`` or existing ``POST .../{id}/submit``). Empty create remains for compatibility.
    """

    def __init__(self, repository: PropertySubmissionRepository) -> None:
        self._repo = repository

    @staticmethod
    def _user_has_role(user: User, role_name: str) -> bool:
        roles = getattr(user, "roles", None) or []
        for r in roles:
            if getattr(r, "name", None) == role_name:
                return True
        return False

    def create_submission(
        self,
        *,
        user: User,
        body: CreatePropertySubmissionRequest | None = None,
    ) -> PropertySubmissionCreateResponse:
        if body is not None and body.payload is not None:
            return self.create_submission_with_payload(user=user, body=body)
        return self._create_submission_empty(user=user)

    def _create_submission_empty(self, *, user: User) -> PropertySubmissionCreateResponse:
        payload = self._build_default_payload()
        submission = PropertyListingSubmission(
            submitted_by=user.id,
            status="draft",
            current_step=1,
            last_completed_step=0,
            payload=payload,
            step_completion=self._build_default_step_completion(),
        )
        try:
            self._repo.create_submission(submission)
            self._repo.commit()
            self._repo.refresh(submission)
            return self._to_create_response(submission)
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def create_submission_with_payload(
        self,
        *,
        user: User,
        body: CreatePropertySubmissionRequest,
    ) -> PropertySubmissionCreateResponse:
        if body.payload is None:
            return self._create_submission_empty(user=user)
        merged = self._merge_into_default_submission_payload(body.payload)
        self._validate_draft_payload_shape(merged)
        step_completion = self._step_completion_for_merged_payload(merged)
        last_completed_step = self._last_completed_from_step_completion(step_completion)
        current_step = max(1, min(8, int(body.current_step)))
        submission = PropertyListingSubmission(
            submitted_by=user.id,
            status="draft",
            current_step=current_step,
            last_completed_step=last_completed_step,
            payload=copy.deepcopy(merged),
            step_completion=step_completion,
        )
        self._sync_review_flags(submission, merged.get("review_submit", {}))
        try:
            self._repo.create_submission(submission)
            self._repo.commit()
            self._repo.refresh(submission)
            return self._to_create_response(submission, include_payload=True)
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def create_and_submit_submission(
        self,
        *,
        user: User,
        body: CreateAndSubmitPropertySubmissionRequest,
    ) -> PropertySubmissionSubmitResponse:
        if not body.confirm_submit:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="confirm_submit must be true")
        merged = self._merge_into_default_submission_payload(body.payload)
        self._validate_draft_payload_shape(merged)
        step_completion = self._step_completion_for_merged_payload(merged)
        last_completed_step = self._last_completed_from_step_completion(step_completion)
        submission = PropertyListingSubmission(
            submitted_by=user.id,
            status="draft",
            current_step=8,
            last_completed_step=last_completed_step,
            payload=copy.deepcopy(merged),
            step_completion=step_completion,
        )
        self._sync_review_flags(submission, merged.get("review_submit", {}))
        errors = self._validate_final_payload(payload=merged, submission=submission)
        if errors:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=errors)
        try:
            self._repo.create_submission(submission)
            self._repo.flush()
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)
        return self._apply_final_submission_persistence(submission=submission, user=user)

    def admin_create_and_approve_submission(
        self,
        *,
        admin_user: User,
        body: CreateAndSubmitPropertySubmissionRequest,
    ) -> PropertySubmissionSubmitResponse:
        """Admin creates a property using the same payload but gets immediate approval.

        This keeps the draft/submission payload identical to the agent flow, but skips the
        pending moderation status by setting the submission to ``approved`` at submit time.
        """
        if not body.confirm_submit:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="confirm_submit must be true")

        merged = self._merge_into_default_submission_payload(body.payload)
        self._validate_draft_payload_shape(merged)
        step_completion = self._step_completion_for_merged_payload(merged)
        last_completed_step = self._last_completed_from_step_completion(step_completion)
        submission = PropertyListingSubmission(
            submitted_by=admin_user.id,
            status="draft",
            current_step=8,
            last_completed_step=last_completed_step,
            payload=copy.deepcopy(merged),
            step_completion=step_completion,
        )
        self._sync_review_flags(submission, merged.get("review_submit", {}))
        errors = self._validate_final_payload(payload=merged, submission=submission)
        if errors:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=errors)

        payload = merged
        now_utc = datetime.now(timezone.utc)
        verified_status_id = 1
        try:
            verified_row = self._repo.get_property_status_by_slug("verified")
            if verified_row is not None:
                verified_status_id = int(verified_row.id)
        except Exception:
            verified_status_id = 1
        try:
            with self._repo.begin_transaction():
                self._repo.create_submission(submission)
                self._repo.flush()

                property_obj = self._upsert_property(submission=submission, payload=payload, user=admin_user)
                self._replace_property_media(property_obj.id, payload.get("media_documents", {}))
                self._replace_property_owners(property_obj.id, payload.get("owner_information", {}))
                self._replace_property_features(property_obj.id, payload.get("amenities", {}))

                # Approved immediately for admin-created properties.
                submission.reviewed_by = admin_user.id
                submission.reviewed_at = now_utc
                submission.review_reason = None
                submission.submitted_at = submission.submitted_at or now_utc
                submission.property_id = property_obj.id
                submission.status = "approved"

                property_obj.property_status_id = verified_status_id
                property_obj.approved_by_user_id = admin_user.id
                property_obj.updated_by_user_id = admin_user.id

            self._repo.commit()
            self._repo.refresh(submission)
            return PropertySubmissionSubmitResponse(
                submission_id=submission.id,
                property_id=property_obj.id,
                status=submission.status,
            )
        except HTTPException:
            self._repo.rollback()
            raise
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def admin_submit_existing_draft_and_approve(
        self,
        *,
        submission_id: uuid.UUID,
        admin_user: User,
        confirm_submit: bool,
    ) -> PropertySubmissionSubmitResponse:
        """Admin submits an existing draft submission and auto-approves it."""
        if not confirm_submit:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="confirm_submit must be true")

        submission = self._repo.get_submission_by_id(submission_id)
        if submission is None or submission.submitted_by != admin_user.id:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")

        if submission.status in {"submitted", "approved"}:
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail="Submission is already finalized")

        payload = submission.payload or self._build_default_payload()
        merged = self._merge_into_default_submission_payload(payload)
        self._validate_draft_payload_shape(merged)
        step_completion = self._step_completion_for_merged_payload(merged)
        submission.step_completion = step_completion
        submission.last_completed_step = self._last_completed_from_step_completion(step_completion)
        submission.current_step = 8
        submission.payload = copy.deepcopy(merged)
        self._sync_review_flags(submission, merged.get("review_submit", {}))
        errors = self._validate_final_payload(payload=merged, submission=submission)
        if errors:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=errors)

        now_utc = datetime.now(timezone.utc)
        verified_status_id = 1
        try:
            verified_row = self._repo.get_property_status_by_slug("verified")
            if verified_row is not None:
                verified_status_id = int(verified_row.id)
        except Exception:
            verified_status_id = 1

        try:
            with self._repo.begin_transaction():
                property_obj = self._upsert_property(submission=submission, payload=merged, user=admin_user)
                self._replace_property_media(property_obj.id, merged.get("media_documents", {}))
                self._replace_property_owners(property_obj.id, merged.get("owner_information", {}))
                self._replace_property_features(property_obj.id, merged.get("amenities", {}))

                submission.reviewed_by = admin_user.id
                submission.reviewed_at = now_utc
                submission.review_reason = None
                submission.submitted_at = submission.submitted_at or now_utc
                submission.property_id = property_obj.id
                submission.status = "approved"

                property_obj.property_status_id = verified_status_id
                property_obj.approved_by_user_id = admin_user.id
                property_obj.updated_by_user_id = admin_user.id

            self._repo.commit()
            self._repo.refresh(submission)
            return PropertySubmissionSubmitResponse(
                submission_id=submission.id,
                property_id=property_obj.id,
                status=submission.status,
            )
        except HTTPException:
            self._repo.rollback()
            raise
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def get_submission(self, *, submission_id: uuid.UUID, user: User) -> PropertySubmissionDetailResponse:
        submission = self._repo.get_submission_by_id(submission_id)
        self._ensure_can_access(submission, user)
        pl = submission.payload or self._build_default_payload()
        sc = self._compute_step_completion_map(pl)
        reviewed_at = (
            submission.reviewed_at.isoformat() if getattr(submission, "reviewed_at", None) else None
        )
        return PropertySubmissionDetailResponse(
            submission_id=submission.id,
            status=submission.status,
            current_step=submission.current_step,
            last_completed_step=self._last_completed_from_step_completion(sc),
            step_completion=sc,
            payload=pl,
            reviewed_by=getattr(submission, "reviewed_by", None),
            reviewed_at=reviewed_at,
            review_reason=getattr(submission, "review_reason", None),
        )

    def patch_submission(
        self,
        *,
        submission_id: uuid.UUID,
        body: PropertySubmissionPatchRequest,
        user: User,
    ) -> PropertySubmissionPatchResponse:
        submission = self._repo.get_submission_by_id(submission_id)
        self._ensure_can_access(submission, user)
        if submission.status in {"submitted", "approved"}:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Submission is locked for editing in current status",
            )

        if body.payload is not None:
            return self._patch_submission_with_full_payload(submission=submission, body=body, _user=user)

        assert body.step is not None
        return self._patch_submission_single_step(submission=submission, body=body, user=user)

    def _patch_submission_with_full_payload(
        self,
        *,
        submission: PropertyListingSubmission,
        body: PropertySubmissionPatchRequest,
        _user: User,
    ) -> PropertySubmissionPatchResponse:
        assert body.payload is not None
        assert body.current_step is not None
        merged = self._merge_into_default_submission_payload(body.payload)
        self._validate_draft_payload_shape(merged)
        self._sync_review_flags(submission, merged.get("review_submit", {}))
        submission.current_step = max(1, min(8, int(body.current_step)))
        sc = self._compute_step_completion_map(merged)
        submission.last_completed_step = self._last_completed_from_step_completion(sc)
        submission.step_completion = sc
        submission.payload = copy.deepcopy(merged)
        if submission.status in {"draft", "in_progress"}:
            submission.status = "draft"
        # Edits after admin rejection: keep `rejected` until agent resubmits.
        saved = STEP_ORDER[submission.current_step - 1]
        try:
            self._repo.commit()
            self._repo.refresh(submission)
            return PropertySubmissionPatchResponse(
                submission_id=submission.id,
                status=submission.status,
                current_step=submission.current_step,
                last_completed_step=submission.last_completed_step,
                saved_step=saved,
                step_completion=submission.step_completion,
                payload=copy.deepcopy(submission.payload or self._build_default_payload()),
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def _patch_submission_single_step(
        self,
        *,
        submission: PropertyListingSubmission,
        body: PropertySubmissionPatchRequest,
        user: User,
    ) -> PropertySubmissionPatchResponse:
        assert body.step is not None
        # Work on deep copies so SQLAlchemy always sees JSON fields as changed.
        payload = copy.deepcopy(submission.payload or self._build_default_payload())
        step_data = body.data or {}
        self._validate_step_patch(step=body.step, data=step_data)
        payload.setdefault(body.step, {})
        if body.step == "owner_information" and isinstance(step_data.get("owners"), list):
            payload[body.step] = self._merge_owner_information_step(
                existing_step=payload[body.step],
                step_data=step_data,
            )
        else:
            payload[body.step] = deep_merge_dict(payload[body.step], step_data)

        if body.step == "review_submit":
            self._sync_review_flags(submission, payload["review_submit"])

        step_completion = self._compute_step_completion_map(payload)
        incoming_step = STEP_INDEX[body.step]
        submission.current_step = self._next_step(current=submission.current_step, incoming=incoming_step, action=body.action)
        submission.last_completed_step = self._last_completed_from_step_completion(step_completion)

        if body.action == "save_draft" and submission.status in {"draft", "in_progress"}:
            submission.status = "draft"
        elif submission.status == "rejected":
            pass
        elif submission.status == "draft":
            submission.status = "in_progress"

        submission.payload = payload
        submission.step_completion = step_completion
        try:
            self._repo.commit()
            self._repo.refresh(submission)
            return PropertySubmissionPatchResponse(
                submission_id=submission.id,
                status=submission.status,
                current_step=submission.current_step,
                last_completed_step=submission.last_completed_step,
                saved_step=body.step,
                step_completion=submission.step_completion,
                payload=copy.deepcopy(submission.payload or self._build_default_payload()),
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def submit_submission(
        self,
        *,
        submission_id: uuid.UUID,
        body: PropertySubmissionSubmitRequest,
        user: User,
    ) -> PropertySubmissionSubmitResponse:
        if not body.confirm_submit:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="confirm_submit must be true")

        submission = self._repo.get_submission_by_id(submission_id)
        self._ensure_can_access(submission, user)
        service_logger.info(
            "property_submission_submit_start submission_id=%s user_id=%s status=%s property_id=%s",
            submission.id,
            user.id,
            submission.status,
            submission.property_id,
        )
        if submission.status == "submitted" and submission.property_id is not None:
            service_logger.info(
                "property_submission_submit_idempotent_return submission_id=%s user_id=%s property_id=%s",
                submission.id,
                user.id,
                submission.property_id,
            )
            return PropertySubmissionSubmitResponse(
                submission_id=submission.id,
                property_id=submission.property_id,
                status=submission.status,
            )
        if submission.status == "submitted" and submission.property_id is None:
            service_logger.info(
                "property_submission_submit_reprocess_missing_property submission_id=%s user_id=%s",
                submission.id,
                user.id,
            )

        if submission.status == "approved":
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Cannot submit when submission is already approved",
            )
        return self._apply_final_submission_persistence(submission=submission, user=user)

    def _apply_final_submission_persistence(
        self,
        *,
        submission: PropertyListingSubmission,
        user: User,
    ) -> PropertySubmissionSubmitResponse:
        """Run final validation, then one transactional write: property + media + owners + features + submitted row.

        On any failure in the try block, ``rollback`` clears the session (including a freshly flushed submission
        from ``create_and_submit``) so no partial normalized property is left visible.
        """
        if submission.status == "approved":
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Cannot submit when submission is already approved",
            )

        payload = submission.payload or self._build_default_payload()
        errors = self._validate_final_payload(payload=payload, submission=submission)
        if errors:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=errors)

        try:
            with self._repo.begin_transaction():
                property_obj = self._upsert_property(submission=submission, payload=payload, user=user)
                self._replace_property_media(property_obj.id, payload.get("media_documents", {}))
                self._replace_property_owners(property_obj.id, payload.get("owner_information", {}))
                self._replace_property_features(property_obj.id, payload.get("amenities", {}))

                submission.reviewed_by = None
                submission.reviewed_at = None
                submission.review_reason = None

                submission.status = "submitted"
                submission.submitted_at = submission.submitted_at or datetime.now(timezone.utc)
                submission.property_id = property_obj.id
            self._repo.commit()
            self._repo.refresh(submission)
            service_logger.info(
                "property_submission_submit_success submission_id=%s user_id=%s property_id=%s",
                submission.id,
                user.id,
                submission.property_id,
            )
            return PropertySubmissionSubmitResponse(
                submission_id=submission.id,
                property_id=property_obj.id,
                status=submission.status,
            )
        except HTTPException:
            self._repo.rollback()
            raise
        except Exception as exc:
            self._repo.rollback()
            service_logger.exception(
                "property_submission_submit_failed submission_id=%s user_id=%s property_id=%s error=%s",
                submission.id,
                user.id,
                getattr(submission, "property_id", None),
                str(exc),
            )
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def delete_submission(self, *, submission_id: uuid.UUID, user: User) -> PropertySubmissionDeleteResponse:
        """Soft delete a draft/rejected/changes requested submission (and its property when linked).

        Does not hard delete any rows; blocked while ``submitted`` or ``approved``.
        """
        submission = self._repo.get_submission_by_id(submission_id)
        self._ensure_can_access(submission, user)
        if submission.status not in {"rejected", "draft", "in_progress", "changes_requested"}:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="This submission cannot be deleted in its current status",
            )
        now_utc = datetime.now(timezone.utc)
        removed_property_id = submission.property_id
        try:
            submission.deleted_at = now_utc
            submission.deleted_by = user.id
            submission.delete_reason = None

            if submission.property_id is not None:
                prop = self._repo.get_property(submission.property_id, include_deleted=True)
                if prop is not None:
                    prop.deleted_at = now_utc
                    prop.deleted_by = user.id
                    prop.delete_reason = None
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)
        return PropertySubmissionDeleteResponse(
            submission_id=submission_id,
            property_id=removed_property_id,
            status="deleted",
            deleted_at=now_utc.isoformat(),
        )

    def delete_submission_with_reason(
        self,
        *,
        submission_id: uuid.UUID,
        user: User,
        reason: str | None,
    ) -> PropertySubmissionDeleteResponse:
        """Compatibility wrapper to support delete reason via query param (soft delete)."""
        submission = self._repo.get_submission_by_id(submission_id)
        self._ensure_can_access(submission, user)
        if submission.status not in {"rejected", "draft", "in_progress", "changes_requested"}:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="This submission cannot be deleted in its current status",
            )
        now_utc = datetime.now(timezone.utc)
        removed_property_id = submission.property_id
        reason_clean = (reason or "").strip() or None
        try:
            submission.deleted_at = now_utc
            submission.deleted_by = user.id
            submission.delete_reason = reason_clean

            if submission.property_id is not None:
                prop = self._repo.get_property(submission.property_id, include_deleted=True)
                if prop is not None:
                    prop.deleted_at = now_utc
                    prop.deleted_by = user.id
                    prop.delete_reason = reason_clean
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)
        return PropertySubmissionDeleteResponse(
            submission_id=submission_id,
            property_id=removed_property_id,
            status="deleted",
            deleted_at=now_utc.isoformat(),
        )

    def admin_soft_delete_submission(
        self,
        *,
        submission_id: uuid.UUID,
        admin_user: User,
        reason: str | None,
    ) -> PropertySubmissionDeleteResponse:
        """Admin soft delete any submission (and linked property)."""
        submission = self._repo.get_submission_by_id(submission_id, include_deleted=True)
        if submission is None or getattr(submission, "deleted_at", None) is not None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")

        now_utc = datetime.now(timezone.utc)
        reason_clean = (reason or "").strip() or None
        removed_property_id = submission.property_id
        try:
            submission.deleted_at = now_utc
            submission.deleted_by = admin_user.id
            submission.delete_reason = reason_clean

            if submission.property_id is not None:
                prop = self._repo.get_property(submission.property_id, include_deleted=True)
                if prop is not None:
                    prop.deleted_at = now_utc
                    prop.deleted_by = admin_user.id
                    prop.delete_reason = reason_clean
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)
        return PropertySubmissionDeleteResponse(
            submission_id=submission.id,
            property_id=removed_property_id,
            status="deleted",
            deleted_at=now_utc.isoformat(),
        )

    def list_admin_submissions(
        self,
        *,
        status: str | None,
        page: int,
        page_size: int,
        include_deleted: bool = False,
    ) -> AdminSubmissionListResponse:
        allowed_statuses = set(PropertySubmissionRepository.ADMIN_VISIBLE_SUBMISSION_STATUSES)
        if status and status not in allowed_statuses:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid status filter")
        rows = self._repo.list_admin_submissions(status=status, page=page, limit=page_size, include_deleted=include_deleted)
        total = self._repo.count_admin_submissions(status=status, include_deleted=include_deleted)
        items = [
            AdminSubmissionListItem(
                submission_id=submission.id,
                submitted_by=submission.submitted_by,
                submitted_by_name=submitted_by_name,
                status=submission.status,
                property_id=submission.property_id,
                agent_user_id=agent_user_id,
                has_assigned_agent=bool(agent_user_id),
                property_hash=property_hash,
                property_title=property_title,
                property_reference_number=property_reference_number,
                current_step=submission.current_step,
                submitted_at=submission.submitted_at.isoformat() if submission.submitted_at else None,
                reviewed_at=submission.reviewed_at.isoformat() if submission.reviewed_at else None,
            )
            for (
                submission,
                submitted_by_name,
                property_hash,
                property_title,
                property_reference_number,
                agent_user_id,
            ) in rows
        ]
        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        return AdminSubmissionListResponse(
            items=items,
            page=page,
            total=total,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
        )

    def list_my_draft_submissions(
        self,
        *,
        user: User,
        page: int,
        page_size: int,
    ):
        """List draft / in-progress submissions without a property row yet (current user).

        This is used by admin UI as well when an admin is using the stepper flow.
        It intentionally contains no agent assignment fields; agent assignment is handled separately.
        """
        rows, total = self._repo.list_draft_submissions_without_property(user_id=user.id, limit=200)
        items = []
        for d in rows:
            title = None
            payload = d.payload if isinstance(d.payload, dict) else None
            if payload:
                basic = payload.get("basic_information") or {}
                t = basic.get("title")
                if isinstance(t, str) and t.strip():
                    title = t.strip()
            items.append(
                {
                    "submission_id": d.id,
                    "status": d.status,
                    "current_step": d.current_step,
                    "last_completed_step": d.last_completed_step,
                    "title": title,
                    "updated_at": d.updated_at,
                    "can_edit": True,
                    "can_delete": True,
                }
            )
        offset = max(page - 1, 0) * page_size
        paged = items[offset : offset + page_size]
        meta = calculate_pagination(page=page, page_size=page_size, total=total)
        return {
            "items": paged,
            "total": total,
            "page": page,
            "pageSize": meta.page_size,
            "totalPages": meta.total_pages,
            "hasNext": meta.has_next,
            "hasPrevious": meta.has_previous,
        }

    def get_admin_submission(self, *, submission_id: uuid.UUID) -> AdminSubmissionDetailResponse:
        submission = self._repo.get_submission_by_id(submission_id)
        if submission is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")
        property_hash: int | None = None
        if submission.property_id is not None:
            prop = self._repo.get_property(submission.property_id)
            if prop is not None:
                try:
                    property_hash = int(getattr(prop, "property_hash", None)) if getattr(prop, "property_hash", None) is not None else None
                except Exception:
                    property_hash = None
        return AdminSubmissionDetailResponse(
            submission_id=submission.id,
            status=submission.status,
            property_id=submission.property_id,
            property_hash=property_hash,
            submitted_by=submission.submitted_by,
            submitted_at=submission.submitted_at.isoformat() if submission.submitted_at else None,
            reviewed_by=submission.reviewed_by,
            reviewed_at=submission.reviewed_at.isoformat() if submission.reviewed_at else None,
            review_reason=submission.review_reason,
            payload=submission.payload or {},
        )

    def review_submission(
        self,
        *,
        submission_id: uuid.UUID,
        admin_user: User,
        body: AdminSubmissionReviewRequest,
    ) -> AdminSubmissionReviewResponse:
        submission = self._repo.get_submission_by_id(submission_id)
        if submission is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")
        if submission.status in {"draft", "in_progress"}:
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail="Cannot review unsubmitted submission")
        if submission.status in {"approved", "rejected"}:
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail="Submission already finalized")
        if body.action in {"changes_requested", "reject"} and not (body.reason or "").strip():
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="reason is required for this action")
        new_status = {
            "approve": "approved",
            "changes_requested": "changes_requested",
            "reject": "rejected",
        }[body.action]

        try:
            submission.status = new_status
            submission.reviewed_by = admin_user.id
            submission.reviewed_at = datetime.now(timezone.utc)
            submission.review_reason = body.reason.strip() if body.reason else None
            # Set catalog status to verified when approved.
            if submission.property_id and new_status == "approved":
                property_obj = self._repo.get_property(submission.property_id)
                if property_obj is not None:
                    verified_status_id = 1
                    try:
                        verified_row = self._repo.get_property_status_by_slug("verified")
                        if verified_row is not None:
                            verified_status_id = int(verified_row.id)
                    except Exception:
                        verified_status_id = 1
                    property_obj.property_status_id = verified_status_id
                    property_obj.approved_by_user_id = admin_user.id
                    property_obj.updated_by_user_id = admin_user.id
            self._repo.commit()
            self._repo.refresh(submission)
            return AdminSubmissionReviewResponse(
                submission_id=submission.id,
                status=submission.status,
                reviewed_by=submission.reviewed_by,
                reviewed_at=submission.reviewed_at.isoformat() if submission.reviewed_at else None,
                review_reason=submission.review_reason,
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def _upsert_property(self, *, submission: PropertyListingSubmission, payload: dict[str, Any], user: User) -> PropertyNormalized:
        basic = payload.get("basic_information", {})
        location = payload.get("location", {})
        details = payload.get("property_details", {})
        pricing = payload.get("pricing", {})
        media = payload.get("media_documents", {})
        purpose = (basic.get("listing_purpose") or "").lower()
        price = Decimal(str(pricing.get("price")))
        selling_price_amount = price if purpose == "sale" else None
        rent_price_amount = price if purpose == "rent" else None

        property_obj = self._repo.get_property(submission.property_id) if submission.property_id else None
        if property_obj is None:
            property_obj = PropertyNormalized(
                category_id=basic["category_id"],
                type_id=basic["type_id"],
                property_status_id=1,
                city_id=location["city_id"],
                location_id=location["area_id"],
                title=basic["title"],
                description=basic.get("description"),
                listing_purpose=basic.get("listing_purpose"),
                address=location.get("address"),
                reference_number=details.get("reference_number"),
                price=price,
                currency=pricing.get("currency"),
                selling_price_amount=selling_price_amount,
                rent_price_amount=rent_price_amount,
                area=self._decimal_or_none(details.get("built_up_area")),
                bedrooms=details.get("bedrooms"),
                bathrooms=details.get("bathrooms"),
                property_age=self._coerce_property_age_int(details.get("property_age")),
                parking_spaces=details.get("parking_spaces"),
                total_floors=details.get("total_floors"),
                completion_status=details.get("completion_status"),
                occupancy=details.get("occupancy"),
                ownership_type=details.get("ownership_type"),
                permit_number=details.get("permit_number"),
                orientation=details.get("orientation"),
                service_charge=self._decimal_or_none(pricing.get("service_charge")),
                maintenance_fee=self._decimal_or_none(pricing.get("maintenance_fee")),
                youtube_url=media.get("youtube_url"),
                virtual_tour_url=media.get("virtual_tour_url"),
                created_by=user.id,
                # If an agent is creating the property, treat them as the listing/assigned agent by default.
                # Admin-created properties intentionally leave this null until explicitly assigned.
                agent_user_id=(user.id if self._user_has_role(user, "agent") else None),
                property_hash=0,
            )
            self._repo.create_property(property_obj)
            self._repo.flush()
            property_obj.property_hash = uuid_to_int_hash(property_obj.id)
            service_logger.info(
                "property_submission_property_created submission_id=%s user_id=%s property_id=%s",
                submission.id,
                user.id,
                property_obj.id,
            )
        else:
            property_obj.category_id = basic["category_id"]
            property_obj.type_id = basic["type_id"]
            property_obj.city_id = location["city_id"]
            property_obj.location_id = location["area_id"]
            property_obj.title = basic["title"]
            property_obj.description = basic.get("description")
            property_obj.listing_purpose = basic.get("listing_purpose")
            property_obj.address = location.get("address")
            property_obj.reference_number = details.get("reference_number")
            property_obj.price = price
            property_obj.currency = pricing.get("currency")
            property_obj.selling_price_amount = selling_price_amount
            property_obj.rent_price_amount = rent_price_amount
            property_obj.area = self._decimal_or_none(details.get("built_up_area"))
            property_obj.bedrooms = details.get("bedrooms")
            property_obj.bathrooms = details.get("bathrooms")
            property_obj.property_age = self._coerce_property_age_int(details.get("property_age"))
            property_obj.parking_spaces = details.get("parking_spaces")
            property_obj.total_floors = details.get("total_floors")
            property_obj.completion_status = details.get("completion_status")
            property_obj.occupancy = details.get("occupancy")
            property_obj.ownership_type = details.get("ownership_type")
            property_obj.permit_number = details.get("permit_number")
            property_obj.orientation = details.get("orientation")
            property_obj.service_charge = self._decimal_or_none(pricing.get("service_charge"))
            property_obj.maintenance_fee = self._decimal_or_none(pricing.get("maintenance_fee"))
            property_obj.youtube_url = media.get("youtube_url")
            property_obj.virtual_tour_url = media.get("virtual_tour_url")
            # Backfill (non-destructive): if this property was created by an agent and has no explicit agent yet,
            # set the creator as the listing/assigned agent.
            if getattr(property_obj, "agent_user_id", None) is None and self._user_has_role(user, "agent"):
                property_obj.agent_user_id = user.id
            service_logger.info(
                "property_submission_property_updated submission_id=%s user_id=%s property_id=%s",
                submission.id,
                user.id,
                property_obj.id,
            )

        self._repo.flush()
        return property_obj

    def _replace_property_owners(self, property_id: uuid.UUID, owner_information: dict[str, Any]) -> None:
        owners = owner_information.get("owners", [])
        self._repo.replace_property_owners(property_id)
        mapped_owner_ids: set[uuid.UUID] = set()
        for owner_row in owners:
            owner_user_id = self._resolve_owner_user_id(owner_row)
            owner = self._repo.get_owner_by_email_or_phone(
                owner_row.get("email"),
                owner_row.get("phone"),
                for_update=True,
            )
            owner_documents = owner_row.get("documents") or []
            if owner is None:
                try:
                    owner = Owner(
                        full_name=owner_row.get("full_name"),
                        email=owner_row.get("email"),
                        phone=owner_row.get("phone"),
                        user_id=owner_user_id,
                        nationality=owner_row.get("nationality"),
                        ssi=owner_row.get("ssi"),
                        address=owner_row.get("address"),
                        documents=owner_documents,
                    )
                    self._repo.add_owner(owner)
                    self._repo.flush()
                    service_logger.info(
                        "property_submission_owner_created property_id=%s owner_id=%s email=%s phone=%s",
                        property_id,
                        owner.owner_id,
                        owner_row.get("email"),
                        owner_row.get("phone"),
                    )
                except IntegrityError:
                    owner = self._repo.get_owner_by_email_or_phone(
                        owner_row.get("email"),
                        owner_row.get("phone"),
                        for_update=True,
                    )
                    if owner is None:
                        raise
                    service_logger.info(
                        "property_submission_owner_reused_after_integrity_conflict property_id=%s owner_id=%s email=%s phone=%s",
                        property_id,
                        owner.owner_id,
                        owner_row.get("email"),
                        owner_row.get("phone"),
                    )
            else:
                owner.user_id = owner_user_id
                owner.full_name = owner_row.get("full_name") or owner.full_name
                owner.nationality = owner_row.get("nationality") or owner.nationality
                owner.ssi = owner_row.get("ssi") or owner.ssi
                owner.address = owner_row.get("address") or owner.address
                owner.documents = self._merge_owner_documents(owner.documents or [], owner_documents)
                service_logger.info(
                    "property_submission_owner_reused property_id=%s owner_id=%s email=%s phone=%s",
                    property_id,
                    owner.owner_id,
                    owner_row.get("email"),
                    owner_row.get("phone"),
                )

            if owner.owner_id in mapped_owner_ids:
                continue
            mapped_owner_ids.add(owner.owner_id)
            self._repo.add_property_owner(
                PropertyOwner(
                    property_id=property_id,
                    owner_id=owner.owner_id,
                    is_active=bool(owner_row.get("is_primary", False)),
                )
            )

    def _replace_property_features(self, property_id: uuid.UUID, amenities: dict[str, Any]) -> None:
        self._repo.replace_property_features(property_id)
        for feature_id in amenities.get("feature_ids", []) or []:
            self._repo.add_property_feature(PropertyFeature(property_id=property_id, feature_id=feature_id))

    def _replace_property_media(self, property_id: uuid.UUID, media_documents: dict[str, Any]) -> None:
        self._repo.replace_property_media(property_id)
        service_logger.info("property_submission_media_replaced property_id=%s", property_id)
        for index, image in enumerate(media_documents.get("images", []) or []):
            self._repo.add_property_media(
                PropertyMedia(
                    property_id=property_id,
                    media_type="image",
                    url=image["url"],
                    is_primary=bool(image.get("is_primary", False)),
                    display_order=image.get("display_order", index),
                    caption=image.get("caption"),
                )
            )
        for index, video in enumerate(media_documents.get("videos", []) or []):
            self._repo.add_property_media(
                PropertyMedia(
                    property_id=property_id,
                    media_type="video",
                    url=video["url"],
                    is_primary=False,
                    display_order=video.get("display_order", index),
                    caption=video.get("caption"),
                )
            )
        for index, document in enumerate(media_documents.get("documents", []) or []):
            self._repo.add_property_media(
                PropertyMedia(
                    property_id=property_id,
                    media_type="document",
                    url=document["url"],
                    is_primary=False,
                    display_order=document.get("display_order", index),
                    caption=document.get("caption") or document.get("file_name"),
                )
            )

    def _validate_step_patch(self, *, step: SubmissionStep, data: dict[str, Any]) -> None:
        if step == "basic_information":
            type_id = data.get("type_id")
            category_id = data.get("category_id")
            if type_id is not None:
                prop_type = self._repo.get_category_type(type_id)
                if prop_type is None:
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid type_id")
                if category_id is not None and prop_type.category_id != category_id:
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="type_id does not belong to category_id")
        elif step == "location":
            area_id = data.get("area_id")
            city_id = data.get("city_id")
            if city_id is not None and self._repo.get_city(city_id) is None:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid city_id")
            if area_id is not None:
                area = self._repo.get_area(area_id)
                if area is None:
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid area_id")
                if city_id is not None and area.city_id != city_id:
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="area_id does not belong to city_id")
        elif step == "owner_information":
            owners = data.get("owners")
            if owners is not None and not isinstance(owners, list):
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="owners must be an array")
            for owner in owners or []:
                if not isinstance(owner, dict):
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Each owner must be an object")
                documents = owner.get("documents")
                if documents is not None and not isinstance(documents, list):
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="owner documents must be an array")
                for document in documents or []:
                    if not isinstance(document, dict) or not document.get("url"):
                        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid owner document payload")
                    self._validate_file_metadata(
                        document,
                        allowed_keys={"file_name", "url"},
                        require_file_name=True,
                        allow_is_primary=False,
                    )
        elif step == "property_details":
            # property_age may be a categorical range string (e.g. "6-10") from the UI, not a float.
            for key in ("bedrooms", "bathrooms", "built_up_area", "parking_spaces", "total_floors"):
                self._ensure_non_negative(data.get(key), key)
        elif step == "pricing":
            for key in ("price", "service_charge", "maintenance_fee"):
                self._ensure_non_negative(data.get(key), key)
        elif step == "amenities":
            feature_ids = data.get("feature_ids")
            if feature_ids is not None:
                if not isinstance(feature_ids, list) or not all(isinstance(item, int) for item in feature_ids):
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="feature_ids must be an array of integers")
                if feature_ids and self._repo.count_existing_features(feature_ids) != len(set(feature_ids)):
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="One or more feature_ids are invalid")
        elif step == "media_documents":
            self._validate_media_payload(data)

    def _validate_media_payload(self, data: dict[str, Any]) -> None:
        for key in ("images", "videos", "documents"):
            if key in data and not isinstance(data[key], list):
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"{key} must be an array")
            for row in data.get(key, []):
                if not isinstance(row, dict) or not row.get("url"):
                    raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Invalid {key} payload")
                allowed_keys = {"file_name", "url", "caption", "display_order"}
                if key == "images":
                    allowed_keys.add("is_primary")
                self._validate_file_metadata(
                    row,
                    allowed_keys=allowed_keys,
                    require_file_name=True,
                    allow_is_primary=(key == "images"),
                )
                if key != "images" and "is_primary" in row:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=f"is_primary is only supported for images",
                    )
                if "display_order" in row and not isinstance(row["display_order"], int):
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail="display_order must be an integer",
                    )

    def _validate_final_payload(self, *, payload: dict[str, Any], submission: PropertyListingSubmission) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        basic = payload.get("basic_information", {})
        location = payload.get("location", {})
        pricing = payload.get("pricing", {})
        review = payload.get("review_submit", {})
        owner_info = payload.get("owner_information", {})
        amenities = payload.get("amenities", {})

        for field in ("listing_purpose", "category_id", "type_id", "title"):
            if not basic.get(field):
                errors.append({"field": f"basic_information.{field}", "message": "This field is required"})
        for field in ("city_id", "area_id"):
            if not location.get(field):
                errors.append({"field": f"location.{field}", "message": "This field is required"})
        if pricing.get("price") in (None, ""):
            errors.append({"field": "pricing.price", "message": "Price is required"})
        if basic.get("listing_purpose") not in {"sale", "rent"}:
            errors.append({"field": "basic_information.listing_purpose", "message": "Must be sale or rent"})

        owners = owner_info.get("owners", [])
        if not owners:
            errors.append({"field": "owner_information.owners", "message": "At least one owner is required"})
        for idx, owner in enumerate(owners):
            if not owner.get("full_name"):
                errors.append({"field": f"owner_information.owners[{idx}].full_name", "message": "Full name is required"})
            if not owner.get("phone") and not owner.get("email"):
                errors.append({"field": f"owner_information.owners[{idx}]", "message": "Email or phone is required"})

        for field in ("terms_accepted", "privacy_accepted", "public_display_authorized", "fees_acknowledged"):
            accepted = review.get(field) if field in review else getattr(submission, field)
            if not accepted:
                errors.append({"field": f"review_submit.{field}", "message": "Must be accepted"})

        self._validate_step_patch(step="basic_information", data=basic)
        self._validate_step_patch(step="location", data=location)
        self._validate_step_patch(step="pricing", data=pricing)
        self._validate_step_patch(step="owner_information", data=owner_info)
        media_docs = payload.get("media_documents", {})
        if media_docs:
            self._validate_step_patch(step="media_documents", data=media_docs)
        if amenities:
            self._validate_step_patch(step="amenities", data=amenities)
        return errors

    @staticmethod
    def _is_nonempty_text(value: Any) -> bool:
        """True if *value* is a non-empty string after strip (used for title, name, phone)."""
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return False

    def _is_basic_information_complete(self, data: dict[str, Any]) -> bool:
        if not data:
            return False
        purpose = str(data.get("listing_purpose") or "").strip().lower()
        if purpose not in {"sale", "rent"}:
            return False
        if not self._is_nonempty_text(data.get("title")):
            return False
        if data.get("category_id") in (None, ""):
            return False
        if data.get("type_id") in (None, ""):
            return False
        return True

    def _is_location_complete(self, data: dict[str, Any]) -> bool:
        if not data:
            return False
        c, a = data.get("city_id"), data.get("area_id")
        if c in (None, "") or a in (None, ""):
            return False
        if not self._is_nonempty_text(data.get("address")):
            return False
        return True

    def _is_owner_information_complete(self, data: dict[str, Any]) -> bool:
        """Match final submit: each owner has full name and at least one of phone or email (non-blank)."""
        owners = data.get("owners")
        if not isinstance(owners, list) or not owners:
            return False
        for owner in owners:
            if not isinstance(owner, dict):
                return False
            if not self._is_nonempty_text(owner.get("full_name")):
                return False
            phone = self._is_nonempty_text(owner.get("phone"))
            em = owner.get("email")
            email = self._is_nonempty_text(em) if em is not None else False
            if not (phone or email):
                return False
        return True

    def _is_property_details_complete(self, data: dict[str, Any]) -> bool:
        if not data or not isinstance(data, dict):
            return False
        for v in data.values():
            if v is None or v is False:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            if isinstance(v, (list, dict)) and not v:
                continue
            return True
        return False

    def _is_pricing_complete(self, data: dict[str, Any]) -> bool:
        p = data.get("price")
        if p in (None, ""):
            return False
        try:
            return float(p) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _is_amenities_complete(data: dict[str, Any]) -> bool:
        """At least one feature id (same as a meaningful amenities selection in the UI)."""
        if not data:
            return False
        ids = data.get("feature_ids")
        if not isinstance(ids, list) or not ids:
            return False
        for x in ids:
            if x in (None, ""):
                continue
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                return True
        return False

    def _is_media_documents_complete(self, data: dict[str, Any]) -> bool:
        """At least one image/video/document row with a URL, or a non-empty YouTube / virtual-tour link."""
        if not data or not isinstance(data, dict):
            return False
        for key in ("images", "videos", "documents"):
            items = data.get(key)
            if not isinstance(items, list):
                continue
            for row in items:
                if isinstance(row, dict) and self._is_nonempty_text(row.get("url")):
                    return True
        for link_key in ("youtube_url", "virtual_tour_url"):
            if self._is_nonempty_text(data.get(link_key)):
                return True
        return False

    def _is_review_submit_complete(self, data: dict[str, Any]) -> bool:
        if not data:
            return False
        for flag in ("terms_accepted", "privacy_accepted", "public_display_authorized", "fees_acknowledged"):
            if not data.get(flag):
                return False
        return True

    def _validate_step_completion(self, step: SubmissionStep, data: dict[str, Any]) -> bool:
        if step == "basic_information":
            return self._is_basic_information_complete(data)
        if step == "location":
            return self._is_location_complete(data)
        if step == "owner_information":
            return self._is_owner_information_complete(data)
        if step == "property_details":
            return self._is_property_details_complete(data)
        if step == "pricing":
            return self._is_pricing_complete(data)
        if step == "amenities":
            return self._is_amenities_complete(data)
        if step == "media_documents":
            return self._is_media_documents_complete(data)
        if step == "review_submit":
            return self._is_review_submit_complete(data)
        return False

    def _compute_step_completion_map(self, payload: dict[str, Any]) -> dict[str, bool]:
        """Recompute all step flags from the merged payload (single source of truth)."""
        return {
            step: self._validate_step_completion(step, self._step_data_for_step_validation(step, payload))
            for step in STEP_ORDER
        }

    def _sync_review_flags(self, submission: PropertyListingSubmission, review_payload: dict[str, Any]) -> None:
        submission.terms_accepted = bool(review_payload.get("terms_accepted", submission.terms_accepted))
        submission.privacy_accepted = bool(review_payload.get("privacy_accepted", submission.privacy_accepted))
        submission.public_display_authorized = bool(
            review_payload.get("public_display_authorized", submission.public_display_authorized)
        )
        submission.fees_acknowledged = bool(review_payload.get("fees_acknowledged", submission.fees_acknowledged))

    def _next_step(self, *, current: int, incoming: int, action: str) -> int:
        if action == "next":
            return min(8, max(current, incoming) + 1)
        if action == "previous":
            return max(1, current - 1)
        return max(current, incoming)

    def _ensure_can_access(self, submission: PropertyListingSubmission | None, user: User) -> None:
        if submission is None or submission.submitted_by != user.id:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")

    def _build_default_payload(self) -> dict[str, Any]:
        return copy.deepcopy(DEFAULT_SUBMISSION_PAYLOAD)

    def _build_default_step_completion(self) -> dict[str, bool]:
        return dict(DEFAULT_STEP_COMPLETION)

    def _merge_into_default_submission_payload(self, incoming: dict[str, Any]) -> dict[str, Any]:
        return deep_merge_dict(self._build_default_payload(), incoming)

    def _validate_draft_payload_shape(self, payload: dict[str, Any]) -> None:
        for step in STEP_ORDER:
            self._validate_step_patch(step=step, data=self._step_data_for_step_validation(step, payload))

    def _step_data_for_step_validation(self, step: SubmissionStep, payload: dict[str, Any]) -> dict[str, Any]:
        step_payload = payload.get(step)
        if not isinstance(step_payload, dict):
            if step == "owner_information":
                return {"owners": []}
            return {}
        data = copy.deepcopy(step_payload)
        if step == "owner_information" and not isinstance(data.get("owners"), list):
            data["owners"] = []
        return data

    def _step_completion_for_merged_payload(self, payload: dict[str, Any]) -> dict[str, bool]:
        return self._compute_step_completion_map(payload)

    def _last_completed_from_step_completion(self, step_completion: dict[str, bool]) -> int:
        last = 0
        for step in STEP_ORDER:
            if step_completion.get(step):
                last = max(last, STEP_INDEX[step])
        return last

    def _to_create_response(
        self,
        submission: PropertyListingSubmission,
        *,
        include_payload: bool = False,
    ) -> PropertySubmissionCreateResponse:
        pl: dict[str, Any] | None
        if include_payload:
            pl = copy.deepcopy(submission.payload or self._build_default_payload())
        else:
            pl = None
        return PropertySubmissionCreateResponse(
            submission_id=submission.id,
            status=submission.status,
            current_step=submission.current_step,
            last_completed_step=submission.last_completed_step,
            step_completion=submission.step_completion or self._build_default_step_completion(),
            payload=pl,
        )

    def _ensure_non_negative(self, value: Any, field: str) -> None:
        if value in (None, ""):
            return
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"{field} must be a non-negative number",
            )
        if num < 0:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"{field} must be non-negative")

    def _coerce_property_age_int(self, value: Any) -> int | None:
        """Persist ``property_age`` to Integer: accept int/float, plain digit strings, or ``lo-hi`` range (midpoint)."""
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, float):
            if value < 0:
                return None
            return int(value)
        s = str(value).strip()
        if s.isdigit():
            return int(s)
        m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", s)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return (lo + hi) // 2
        return None

    def _decimal_or_none(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    def _validate_file_metadata(
        self,
        row: dict[str, Any],
        *,
        allowed_keys: set[str],
        require_file_name: bool,
        allow_is_primary: bool,
    ) -> None:
        unknown_keys = set(row.keys()) - allowed_keys
        if unknown_keys:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Unsupported file metadata fields: {', '.join(sorted(unknown_keys))}",
            )
        if require_file_name and not isinstance(row.get("file_name"), str):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_name is required")
        for key in ("file_name", "caption"):
            if key in row and row[key] is not None and not isinstance(row[key], str):
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"{key} must be a string")
        if allow_is_primary and "is_primary" in row and not isinstance(row["is_primary"], bool):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="is_primary must be a boolean")

    def _resolve_owner_user_id(self, owner_row: dict[str, Any]) -> uuid.UUID | None:
        email = owner_row.get("email")
        phone = owner_row.get("phone")
        user_from_email = self._repo.get_user_by_email(email) if email else None
        user_from_phone = self._repo.get_user_by_phone(phone) if phone else None
        if user_from_email and user_from_phone and user_from_email.id != user_from_phone.id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Owner email and phone resolve to different users",
            )
        if user_from_email:
            return user_from_email.id
        if user_from_phone:
            return user_from_phone.id
        return None

    def _merge_owner_documents(self, existing_docs: list[dict[str, Any]], new_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not new_docs:
            return existing_docs
        dedup_map: dict[str, dict[str, Any]] = {}
        for doc in existing_docs + new_docs:
            if not isinstance(doc, dict):
                continue
            url = str(doc.get("url")).strip() if doc.get("url") else ""
            if not url:
                continue
            dedup_map[url] = doc
        return list(dedup_map.values())

    def _merge_owner_information_step(
        self,
        *,
        existing_step: dict[str, Any],
        step_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge owner_information without wiping prior owner rows or uploaded documents.

        ``deep_merge_dict`` replaces whole lists; ``owners`` is a list, so a PATCH that
        resends name/phone without ``documents`` would otherwise erase stored file refs.
        """
        step_snapshot = copy.deepcopy(existing_step)
        owners_incoming = step_data["owners"]
        step_without_owners = {k: v for k, v in step_data.items() if k != "owners"}
        merged_step = deep_merge_dict(existing_step, step_without_owners)
        prev_owners = step_snapshot.get("owners") or []
        merged_rows: list[Any] = []
        for i, new_owner in enumerate(owners_incoming):
            if not isinstance(new_owner, dict):
                merged_rows.append(new_owner)
                continue
            prev = prev_owners[i] if i < len(prev_owners) and isinstance(prev_owners[i], dict) else {}
            new_without_docs = {k: v for k, v in new_owner.items() if k != "documents"}
            merged_owner = deep_merge_dict(prev, new_without_docs)
            if "documents" in new_owner:
                docs_in = new_owner.get("documents")
                if not isinstance(docs_in, list):
                    if prev.get("documents"):
                        merged_owner["documents"] = copy.deepcopy(prev["documents"])
                elif len(docs_in) == 0:
                    merged_owner["documents"] = []
                else:
                    merged_owner["documents"] = self._merge_owner_documents(
                        prev.get("documents") or [],
                        docs_in,
                    )
            elif prev.get("documents"):
                merged_owner["documents"] = copy.deepcopy(prev["documents"])
            merged_rows.append(merged_owner)
        merged_step["owners"] = merged_rows
        return merged_step
