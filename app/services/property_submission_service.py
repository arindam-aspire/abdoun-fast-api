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
    DEFAULT_STEP_COMPLETION,
    DEFAULT_SUBMISSION_PAYLOAD,
    STEP_INDEX,
    CreatePropertySubmissionRequest,
    PropertySubmissionCreateResponse,
    PropertySubmissionDetailResponse,
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
    """Business logic for draft stepper save/resume/submit flow."""

    def __init__(self, repository: PropertySubmissionRepository) -> None:
        self._repo = repository

    def create_submission(
        self,
        *,
        user: User,
        body: CreatePropertySubmissionRequest | None = None,
    ) -> PropertySubmissionCreateResponse:
        payload = self._build_default_payload()
        if body and body.payload:
            for key, value in body.payload.items():
                if key in payload and isinstance(value, dict):
                    payload[key].update(value)

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

    def get_submission(self, *, submission_id: uuid.UUID, user: User) -> PropertySubmissionDetailResponse:
        submission = self._repo.get_submission_by_id(submission_id)
        self._ensure_can_access(submission, user)
        return PropertySubmissionDetailResponse(
            submission_id=submission.id,
            status=submission.status,
            current_step=submission.current_step,
            last_completed_step=submission.last_completed_step,
            step_completion=submission.step_completion or self._build_default_step_completion(),
            payload=submission.payload or self._build_default_payload(),
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
        if submission.status in {"submitted", "approved", "rejected"}:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Submission is locked for editing in current status",
            )

        # Work on deep copies so SQLAlchemy always sees JSON fields as changed.
        payload = copy.deepcopy(submission.payload or self._build_default_payload())
        step_completion = copy.deepcopy(
            submission.step_completion or self._build_default_step_completion()
        )
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

        is_complete = self._validate_step_completion(body.step, payload[body.step])
        step_completion[body.step] = is_complete

        incoming_step = STEP_INDEX[body.step]
        submission.current_step = self._next_step(current=submission.current_step, incoming=incoming_step, action=body.action)
        if is_complete:
            submission.last_completed_step = max(submission.last_completed_step, incoming_step)

        if body.action == "save_draft" and submission.status in {"draft", "in_progress"}:
            submission.status = "draft"
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

        if submission.status in {"approved", "rejected"}:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Cannot submit when submission is approved or rejected",
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

                submission.status = "submitted"
                submission.submitted_at = submission.submitted_at or datetime.now(timezone.utc)
                submission.property_id = property_obj.id
            # Ensure persistence even when begin_transaction() reuses an existing implicit transaction.
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
                submission.property_id,
                str(exc),
            )
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=ErrorMessages.REQUEST_FAILED)

    def list_admin_submissions(
        self,
        *,
        status: str | None,
        page: int,
        limit: int,
    ) -> AdminSubmissionListResponse:
        allowed_statuses = {"submitted", "changes_requested", "approved", "rejected"}
        if status and status not in allowed_statuses:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid status filter")
        rows = self._repo.list_admin_submissions(status=status, page=page, limit=limit)
        total = self._repo.count_admin_submissions(status=status)
        items = [
            AdminSubmissionListItem(
                submission_id=row.id,
                submitted_by=row.submitted_by,
                status=row.status,
                property_id=row.property_id,
                current_step=row.current_step,
                submitted_at=row.submitted_at.isoformat() if row.submitted_at else None,
                reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
            )
            for row in rows
        ]
        return AdminSubmissionListResponse(items=items, page=page, limit=limit, total=total)

    def get_admin_submission(self, *, submission_id: uuid.UUID) -> AdminSubmissionDetailResponse:
        submission = self._repo.get_submission_by_id(submission_id)
        if submission is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")
        return AdminSubmissionDetailResponse(
            submission_id=submission.id,
            status=submission.status,
            property_id=submission.property_id,
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
            # Keep property_status alignment with existing convention (1 as active).
            if submission.property_id and new_status == "approved":
                property_obj = self._repo.get_property(submission.property_id)
                if property_obj is not None:
                    property_obj.property_status_id = 1
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

    def _validate_step_completion(self, step: SubmissionStep, data: dict[str, Any]) -> bool:
        if step == "basic_information":
            return bool(data.get("listing_purpose") and data.get("category_id") and data.get("type_id"))
        if step == "location":
            return bool(data.get("city_id") and data.get("area_id"))
        if step == "owner_information":
            return isinstance(data.get("owners", []), list)
        if step == "pricing":
            return data.get("price") not in (None, "")
        if step == "review_submit":
            return all(
                bool(data.get(flag))
                for flag in ("terms_accepted", "privacy_accepted", "public_display_authorized", "fees_acknowledged")
            )
        return True

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

    def _to_create_response(self, submission: PropertyListingSubmission) -> PropertySubmissionCreateResponse:
        return PropertySubmissionCreateResponse(
            submission_id=submission.id,
            status=submission.status,
            current_step=submission.current_step,
            last_completed_step=submission.last_completed_step,
            step_completion=submission.step_completion or self._build_default_step_completion(),
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
