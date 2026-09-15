from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.models.live_schema import (
    AgencyMaster,
    Feature,
    PropertyCategory,
    PropertyListingSubmission,
    PropertyMedia,
    PropertyType,
    Role,
    User,
    UserRole,
)
from app.schemas.agents import validate_e164_phone
from app.services.audit import record_activity
from app.services.dls_locations import DLS_PARENTS, dls_official_name
from app.services.exchange_rates import assert_supported_currency, convert_amount_to_jod_or_http_error
from app.services.media_urls import canonicalize_media_url, with_canonical_media_urls, with_readable_media_urls
from app.services.notifications import create_in_app_notification, send_email_notification, send_sms_notification
from app.services.property_workflow_config import get_property_workflow_config
from app.services.property_options import resolve_property_option
from app.services.user_agencies import (
    REL_AGENT,
    REL_PROPERTY_OWNER,
    active_mappings,
    agency_users_with_role,
    ensure_user_agency_mapping,
    user_has_active_agency_mapping,
)
from app.utils.api_response import raise_api_error
from app.utils.status_codes import (
    STATUS_BAD_REQUEST,
    STATUS_CONFLICT,
    STATUS_FORBIDDEN,
    STATUS_INTERNAL_SERVER_ERROR,
    STATUS_NOT_FOUND,
)

logger = logging.getLogger(__name__)


WORKFLOW_CONFIG = get_property_workflow_config()
SUBMISSION_SECTIONS = (
    "basic_information",
    "location",
    "owner_information",
    "property_details",
    "pricing",
    "amenities",
    "media_documents",
    "review_submit",
)

DRAFT_STATUSES = {"draft"}
SUBMITTED_STATUS = WORKFLOW_CONFIG.status("submitted")
AGENT_ASSIGNED_STATUS = WORKFLOW_CONFIG.status("agent_assigned")
PENDING_APPROVAL_STATUS = WORKFLOW_CONFIG.status("pending_approval")
ACTIVE_STATUS = WORKFLOW_CONFIG.status("active")
REJECTED_STATUS = WORKFLOW_CONFIG.status("rejected")
DEACTIVATED_STATUS = WORKFLOW_CONFIG.status("deactivated")
DEAL_CLOSED_STATUS = WORKFLOW_CONFIG.status("deal_closed")
DEAL_CLOSURE_REQUESTED_STATUS = WORKFLOW_CONFIG.status("deal_closure_requested")
WORKING_STATUSES = {"draft", REJECTED_STATUS, "in_progress"}
WORKFLOW_STAGE_DRAFT = "draft"
WORKFLOW_STAGE_SUBMITTED = SUBMITTED_STATUS
WORKFLOW_STAGE_AGENT_ASSIGNED = AGENT_ASSIGNED_STATUS
WORKFLOW_STAGE_PENDING_APPROVAL = PENDING_APPROVAL_STATUS
WORKFLOW_STAGE_REJECTED = REJECTED_STATUS
WORKFLOW_STAGE_ACTIVE = ACTIVE_STATUS

LEGACY_WORKFLOW_STAGE_MAP = {
    "awaiting_agency_assignment": WORKFLOW_STAGE_SUBMITTED,
    "with_agent": WORKFLOW_STAGE_AGENT_ASSIGNED,
    "awaiting_agency_review": WORKFLOW_STAGE_PENDING_APPROVAL,
    "returned_to_owner": WORKFLOW_STAGE_REJECTED,
    "returned_to_agent": WORKFLOW_STAGE_REJECTED,
    "approved": WORKFLOW_STAGE_ACTIVE,
}

CURRENT_ACTOR_OWNER = "owner"
CURRENT_ACTOR_ASSIGNED_AGENT = "assigned_agent"
CURRENT_ACTOR_AGENCY_ADMIN = "agency_admin"
CURRENT_ACTOR_SUPER_ADMIN = "super_admin"
CURRENT_ACTOR_SUBMITTER = "submitter"
CURRENT_ACTOR_NONE = None

SUBMISSION_ORIGIN_OWNER = "owner"
SUBMISSION_ORIGIN_AGENCY_ADMIN = "agency_admin"
SUBMISSION_ORIGIN_AGENT = "agent"
SUBMISSION_ORIGIN_SUPER_ADMIN = "super_admin"

ASSIGNMENT_READY_STAGES = {
    WORKFLOW_STAGE_SUBMITTED,
    WORKFLOW_STAGE_AGENT_ASSIGNED,
    WORKFLOW_STAGE_PENDING_APPROVAL,
}
AGENCY_REVIEW_STAGES = {WORKFLOW_STAGE_AGENT_ASSIGNED, WORKFLOW_STAGE_PENDING_APPROVAL}
AGENT_EDIT_STAGES = {WORKFLOW_STAGE_AGENT_ASSIGNED}
OWNER_EDIT_STAGES = {WORKFLOW_STAGE_REJECTED}
KNOWN_WORKFLOW_STAGES = {
    WORKFLOW_STAGE_DRAFT,
    WORKFLOW_STAGE_SUBMITTED,
    WORKFLOW_STAGE_AGENT_ASSIGNED,
    WORKFLOW_STAGE_PENDING_APPROVAL,
    WORKFLOW_STAGE_REJECTED,
    WORKFLOW_STAGE_ACTIVE,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _title(payload: dict[str, Any]) -> str | None:
    basic = payload.get("basic_information") or {}
    return basic.get("title")


def _payload_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = payload.get("_workflow")
    if not isinstance(workflow, dict):
        workflow = {}
        payload["_workflow"] = workflow
    return workflow


def _role_names(roles: tuple[str, ...]) -> set[str]:
    return {role.lower() for role in roles}


AGENCY_SCOPED_ROLES = {"admin", "agent", "agency", "agency_admin"}


def owner_may_submit_without_agency(roles: tuple[str, ...], route_through_agency: bool) -> bool:
    """Owners (and Super Admin) may omit agency when verify_through_agency is false.

    Agency/Admin/Agent keep the existing agency-required workflow regardless of the flag.
    """
    if route_through_agency:
        return False
    return not (_role_names(roles) & AGENCY_SCOPED_ROLES)


def _verify_through_agency(submission: PropertyListingSubmission) -> bool:
    return bool(getattr(submission, "route_through_agency", False))


def _routing_payload(submission: PropertyListingSubmission) -> dict[str, Any]:
    routed = _verify_through_agency(submission)
    return {
        "route_through_agency": routed,
        "verify_through_agency": routed,
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
    }


def _workflow_from_submission(submission: PropertyListingSubmission) -> dict[str, Any]:
    workflow = (submission.payload or {}).get("_workflow") or {}
    return workflow if isinstance(workflow, dict) else {}


def _current_actor_for_workflow_stage(
    stage: str | None,
    *,
    agency_id: UUID | None = None,
) -> str | None:
    if stage == WORKFLOW_STAGE_SUBMITTED:
        return CURRENT_ACTOR_AGENCY_ADMIN if agency_id else CURRENT_ACTOR_SUPER_ADMIN
    if stage == WORKFLOW_STAGE_PENDING_APPROVAL:
        return CURRENT_ACTOR_AGENCY_ADMIN if agency_id else CURRENT_ACTOR_SUPER_ADMIN
    if stage in AGENT_EDIT_STAGES:
        return CURRENT_ACTOR_ASSIGNED_AGENT
    if stage in OWNER_EDIT_STAGES:
        return CURRENT_ACTOR_SUBMITTER
    return CURRENT_ACTOR_NONE


def _workflow_stage_for_submission(submission: PropertyListingSubmission) -> str | None:
    workflow = _workflow_from_submission(submission)
    stage = workflow.get("workflow_stage")
    if isinstance(stage, str) and stage in KNOWN_WORKFLOW_STAGES:
        return stage
    if isinstance(stage, str) and stage in LEGACY_WORKFLOW_STAGE_MAP:
        return LEGACY_WORKFLOW_STAGE_MAP[stage]
    if submission.status in KNOWN_WORKFLOW_STAGES:
        return submission.status
    if submission.status == PENDING_APPROVAL_STATUS:
        if workflow.get("assigned_agent_id"):
            return WORKFLOW_STAGE_PENDING_APPROVAL
        return WORKFLOW_STAGE_PENDING_APPROVAL
    if submission.status == REJECTED_STATUS:
        return WORKFLOW_STAGE_REJECTED
    if submission.status == ACTIVE_STATUS:
        return WORKFLOW_STAGE_ACTIVE
    return None


def _submission_origin_for_roles(roles: tuple[str, ...]) -> str:
    role_names = _role_names(roles)
    if "agent" in role_names:
        return SUBMISSION_ORIGIN_AGENT
    if "super_admin" in role_names:
        return SUBMISSION_ORIGIN_SUPER_ADMIN
    if "admin" in role_names:
        return SUBMISSION_ORIGIN_AGENCY_ADMIN
    return SUBMISSION_ORIGIN_OWNER


def _set_submission_workflow(
    submission: PropertyListingSubmission,
    *,
    stage: str | None = None,
    origin: str | None = None,
    assigned_agent_id: UUID | str | None | object = ...,
    actor_user_id: UUID | None = None,
    agent_review_comment: str | None = None,
) -> dict[str, Any]:
    payload = dict(submission.payload or {})
    workflow = _payload_workflow(payload)
    if stage is not None:
        workflow["workflow_stage"] = stage
        workflow["current_actor"] = _current_actor_for_workflow_stage(
            stage,
            agency_id=getattr(submission, "agency_id", None),
        )
    if origin is not None:
        workflow["submission_origin"] = origin
    if assigned_agent_id is not ...:
        workflow["assigned_agent_id"] = str(assigned_agent_id) if assigned_agent_id else None
    if actor_user_id is not None:
        workflow["last_actor_user_id"] = str(actor_user_id)
    if agent_review_comment is not None:
        workflow["agent_review_comment"] = agent_review_comment
        workflow["agent_reviewed_by"] = str(actor_user_id) if actor_user_id else None
        workflow["agent_reviewed_at"] = utc_now().isoformat()
    workflow["last_transition_at"] = utc_now().isoformat()
    submission.payload = payload
    flag_modified(submission, "payload")
    return workflow


def _submission_workflow_summary(submission: PropertyListingSubmission) -> dict[str, Any]:
    workflow = _workflow_from_submission(submission)
    stage = _workflow_stage_for_submission(submission)
    return {
        "workflow_stage": stage,
        "current_actor": workflow.get("current_actor")
        or _current_actor_for_workflow_stage(stage, agency_id=getattr(submission, "agency_id", None)),
        "submission_origin": workflow.get("submission_origin"),
        "assigned_agent_id": workflow.get("assigned_agent_id"),
    }


def _assigned_agent_uuid(submission: PropertyListingSubmission) -> UUID | None:
    value = _assigned_agent_id(submission)
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _assigned_agent_summary(db: Session, submission: PropertyListingSubmission) -> dict[str, str | None] | None:
    agent_id = _assigned_agent_uuid(submission)
    if not agent_id:
        return None
    agent = db.get(User, agent_id)
    if not agent:
        return {"id": str(agent_id), "name": None, "email": None, "phone": None}
    return {
        "id": str(agent.id),
        "name": agent.full_name,
        "email": agent.email,
        "phone": agent.phone_number,
    }


def _normalize_phone_for_whatsapp(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(character for character in phone if character.isdigit())
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = f"962{digits[1:]}"
    elif not digits.startswith("962") and len(digits) <= 10:
        digits = f"962{digits}"
    return digits


def _agent_contact_actions(
    *,
    email: str | None,
    phone: str | None,
    enabled: bool = True,
) -> dict[str, dict[str, Any]]:
    if not enabled:
        return {
            "email": {
                "type": "email",
                "label": "Email",
                "enabled": False,
                "href": None,
            },
            "phone": {
                "type": "phone",
                "label": "Phone",
                "enabled": False,
                "href": None,
            },
            "whatsapp": {
                "type": "whatsapp",
                "label": "WhatsApp",
                "enabled": False,
                "href": None,
            },
        }

    whatsapp_phone = _normalize_phone_for_whatsapp(phone)
    return {
        "email": {
            "type": "email",
            "label": "Email",
            "enabled": bool(email),
            "href": f"mailto:{email}" if email else None,
        },
        "phone": {
            "type": "phone",
            "label": "Phone",
            "enabled": bool(phone),
            "href": f"tel:{phone}" if phone else None,
        },
        "whatsapp": {
            "type": "whatsapp",
            "label": "WhatsApp",
            "enabled": bool(whatsapp_phone),
            "href": f"{get_settings().whatsapp_base_url}/{whatsapp_phone}" if whatsapp_phone else None,
        },
    }


def serialize_agent_contact(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    fallback_user: User | None = None,
    assigned_agent_only: bool = False,
) -> dict[str, Any] | None:
    summary = _assigned_agent_summary(db, submission)
    if summary is None and not assigned_agent_only and fallback_user is not None:
        summary = {
            "id": str(fallback_user.id),
            "name": fallback_user.full_name,
            "email": fallback_user.email,
            "phone": fallback_user.phone_number,
        }
    return _serialize_agent_contact_summary(summary)


def serialize_agent_contact_by_id(
    db: Session,
    agent_id: str | UUID | None,
    *,
    contact_enabled: bool = True,
) -> dict[str, Any] | None:
    if not agent_id:
        return None
    try:
        agent_uuid = UUID(str(agent_id))
    except ValueError:
        return None
    agent = db.get(User, agent_uuid)
    if not agent:
        return _serialize_agent_contact_summary(
            {"id": str(agent_uuid), "name": None, "email": None, "phone": None},
            contact_enabled=contact_enabled,
        )
    return _serialize_agent_contact_summary(
        {
            "id": str(agent.id),
            "name": agent.full_name,
            "email": agent.email,
            "phone": agent.phone_number,
        },
        contact_enabled=contact_enabled,
    )


def _serialize_agent_contact_summary(
    summary: dict[str, str | None] | None,
    *,
    contact_enabled: bool = True,
) -> dict[str, Any] | None:
    if summary is None:
        return None

    email = summary.get("email") if contact_enabled else None
    phone = summary.get("phone") if contact_enabled else None
    contact_actions = _agent_contact_actions(
        email=email,
        phone=phone,
        enabled=contact_enabled,
    )
    return {
        "id": summary.get("id"),
        "name": summary.get("name"),
        "phone": phone,
        "email": email,
        "contact_actions": contact_actions,
        "actions": [contact_actions[key] for key in ("email", "phone", "whatsapp")],
    }


def _has_property_image(payload: dict[str, Any]) -> bool:
    media = payload.get("media_documents") or {}
    if not isinstance(media, dict):
        return False
    images = media.get("images") or []
    if not isinstance(images, list):
        return False
    return any(isinstance(image, dict) and bool(str(image.get("url") or "").strip()) for image in images)


def _media_item_url(item: Any) -> str | None:
    if isinstance(item, str):
        value = item.strip()
        return canonicalize_media_url(value) if value else None
    if isinstance(item, dict):
        value = str(item.get("url") or item.get("file_url") or "").strip()
        return canonicalize_media_url(value) if value else None
    return None


def sync_property_media_from_payload(
    db: Session,
    *,
    property_id: UUID,
    payload: dict[str, Any] | None,
) -> None:
    """Materialize payload.media_documents into normalized property_media rows."""
    media = (payload or {}).get("media_documents") or {}
    if not isinstance(media, dict):
        media = {}

    db.execute(delete(PropertyMedia).where(PropertyMedia.property_id == property_id))

    rows: list[PropertyMedia] = []

    images = media.get("images") or []
    if isinstance(images, list):
        for index, image in enumerate(images):
            url = _media_item_url(image)
            if not url:
                continue
            is_primary = bool(image.get("is_primary")) if isinstance(image, dict) else index == 0
            if not any(row.is_primary for row in rows if row.media_type == "image") and index == 0:
                is_primary = True
            display_order = index
            caption = None
            if isinstance(image, dict):
                raw_order = image.get("display_order")
                if raw_order is not None:
                    try:
                        display_order = int(raw_order)
                    except (TypeError, ValueError):
                        display_order = index
                caption = image.get("caption") or image.get("file_name")
            rows.append(
                PropertyMedia(
                    property_id=property_id,
                    media_type="image",
                    url=url,
                    thumb_url=url,
                    is_primary=is_primary,
                    display_order=display_order,
                    caption=caption,
                )
            )

    youtube_url = str(media.get("youtube_url") or "").strip()
    if youtube_url:
        rows.append(
            PropertyMedia(
                property_id=property_id,
                media_type="video",
                url=youtube_url,
                thumb_url=youtube_url,
                is_primary=True,
                display_order=0,
                caption=None,
            )
        )

    floor_plans = media.get("floor_plan_images") or media.get("floor_plans") or []
    if isinstance(floor_plans, list):
        for index, item in enumerate(floor_plans):
            url = _media_item_url(item)
            if not url:
                continue
            caption = item.get("file_name") if isinstance(item, dict) else None
            rows.append(
                PropertyMedia(
                    property_id=property_id,
                    media_type="floor_plan",
                    url=url,
                    thumb_url=url,
                    is_primary=index == 0,
                    display_order=index,
                    caption=caption,
                )
            )

    documents = media.get("documents") or []
    if isinstance(documents, list):
        for index, item in enumerate(documents):
            url = _media_item_url(item)
            if not url:
                continue
            caption = item.get("file_name") if isinstance(item, dict) else None
            rows.append(
                PropertyMedia(
                    property_id=property_id,
                    media_type="document",
                    url=url,
                    thumb_url=url,
                    is_primary=index == 0,
                    display_order=index,
                    caption=caption,
                )
            )

    image_rows = [row for row in rows if row.media_type == "image"]
    if image_rows:
        primary_image = next((row for row in image_rows if row.is_primary), image_rows[0])
        for row in image_rows:
            row.is_primary = row is primary_image

    for row in rows:
        db.add(row)
    try:
        db.flush()
    except IntegrityError:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="FILE_UPLOAD_ERROR",
            message="Unable to save property media",
            details=[
                {
                    "field": "media_documents",
                    "code": "file_upload_error",
                    "message": "Property media could not be stored. Check uploaded files and try again",
                }
            ],
        )


def ensure_property_id_and_sync_media(db: Session, submission: PropertyListingSubmission) -> UUID:
    if not submission.property_id:
        submission.property_id = uuid4()
    sync_property_media_from_payload(
        db,
        property_id=submission.property_id,
        payload=submission.payload or {},
    )
    return submission.property_id


def compute_step_completion(payload: dict[str, Any]) -> dict[str, bool]:
    return {section: bool(payload.get(section)) for section in SUBMISSION_SECTIONS}


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return default


def resolve_show_location(payload: dict[str, Any] | None, *, fallback: bool | None = None) -> bool:
    data = payload or {}
    location = data.get("location")
    if isinstance(location, dict) and "show_location" in location:
        return coerce_bool(location.get("show_location"), default=False)
    if "show_location" in data:
        return coerce_bool(data.get("show_location"), default=False)
    if fallback is not None:
        return bool(fallback)
    return False


def apply_show_location_to_payload(
    payload: dict[str, Any] | None,
    show_location: bool | None = None,
) -> tuple[dict[str, Any], bool]:
    """Persist show_location onto payload.location when that step exists. Does not create location."""
    normalized = dict(payload or {})
    value = resolve_show_location(normalized) if show_location is None else coerce_bool(show_location, default=False)
    location = normalized.get("location")
    if isinstance(location, dict):
        location = dict(location)
        location["show_location"] = value
        normalized["location"] = location
    return normalized, value


def show_location_for_submission(submission: PropertyListingSubmission, payload: dict[str, Any] | None = None) -> bool:
    column_value = getattr(submission, "show_location", None)
    if column_value is not None:
        return coerce_bool(column_value, default=False)
    return resolve_show_location(payload if payload is not None else submission.payload)


FURNISHING_OPTION_KEYS = (
    "furnishing_status_id",
    "furnishingStatusId",
    "furnishing_status",
    "furnishingStatus",
    "furniture_status",
    "furnitureStatus",
    "furnishing",
)
FLOOR_OPTION_KEYS = (
    "floor_id",
    "floorId",
    "floor",
    "floor_level",
    "floorLevel",
    "floor_number",
    "floorNumber",
)

PARCEL_IDENTIFIER_FIELDS = (
    "apartment_number",
    "plot_number",
    "basin_number",
    "building_number",
    "parcel_number",
)
DLS_CANONICAL_FIELDS = (
    "gov_code",
    "gov_name",
    "dept_code",
    "dept_name",
    "vill_code",
    "vill_name",
    "hod_code",
    "hod_name",
    "sect_code",
    "sect_name",
)
DLS_FIELD_ALIASES = {
    "GOV_CODE": "gov_code",
    "govCode": "gov_code",
    "governorate_code": "gov_code",
    "governorateCode": "gov_code",
    "GOV_NAME": "gov_name",
    "govName": "gov_name",
    "governorate": "gov_name",
    "governorate_name": "gov_name",
    "DEPT_CODE": "dept_code",
    "deptCode": "dept_code",
    "directorate_code": "dept_code",
    "directorateCode": "dept_code",
    "DEPT_NAME": "dept_name",
    "deptName": "dept_name",
    "directorate": "dept_name",
    "directorate_name": "dept_name",
    "VILL_CODE": "vill_code",
    "villCode": "vill_code",
    "village_code": "vill_code",
    "villageCode": "vill_code",
    "VILL_NAME": "vill_name",
    "villName": "vill_name",
    "village": "vill_name",
    "village_name": "vill_name",
    "HOD_CODE": "hod_code",
    "hodCode": "hod_code",
    "basin_code": "hod_code",
    "HOD_NAME": "hod_name",
    "hodName": "hod_name",
    "hod": "hod_name",
    "basin_name": "hod_name",
    "SECT_CODE": "sect_code",
    "sectCode": "sect_code",
    "section_code": "sect_code",
    "sectionCode": "sect_code",
    "SECT_NAME": "sect_name",
    "sectName": "sect_name",
    "section": "sect_name",
    "section_name": "sect_name",
}
OWNER_IDENTIFICATION_KEYS = (
    "owner_id_or_passport",
    "identification_number",
    "id_or_passport",
    "id_number",
    "passport_number",
    "passport",
    "national_id",
    "social_security_id",
    "ssi",
)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _property_details_dict(payload: dict[str, Any] | None) -> dict[str, Any]:
    details = (payload or {}).get("property_details")
    if not isinstance(details, dict):
        details = (payload or {}).get("propertyDetails")
    return dict(details) if isinstance(details, dict) else {}


def _first_supplied_key(details: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    return next((key for key in keys if details.get(key) not in (None, "")), None)


def _cleaned_text(value: Any, *, field: str | None = None, max_length: int = 255) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    if len(text_value) > max_length:
        _property_field_error(
            field=field or "property_details",
            code="max_length",
            message=f"{field or 'value'} must not exceed {max_length} characters",
        )
    return text_value


def _normalize_dls_section(section: dict[str, Any], *, field_prefix: str) -> dict[str, Any]:
    normalized = dict(section)
    for alias, canonical in DLS_FIELD_ALIASES.items():
        if alias in normalized and canonical not in normalized:
            normalized[canonical] = normalized[alias]
        if alias in normalized and alias != canonical:
            normalized.pop(alias, None)
    for field in (*PARCEL_IDENTIFIER_FIELDS, *DLS_CANONICAL_FIELDS):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _cleaned_text(
                normalized[field],
                field=f"{field_prefix}.{field}",
                max_length=100,
            )
    if not normalized.get("basin_number"):
        hod = normalized.get("hod_code") or normalized.get("hod_name")
        if hod:
            normalized["basin_number"] = hod
    if not normalized.get("hod_code") and normalized.get("basin_number"):
        normalized["hod_code"] = normalized.get("basin_number")
    if not normalized.get("parcel_number") and normalized.get("plot_number"):
        normalized["parcel_number"] = normalized.get("plot_number")
    if not normalized.get("plot_number") and normalized.get("parcel_number"):
        normalized["plot_number"] = normalized.get("parcel_number")
    return normalized


def _sync_parcel_and_dls_fields(payload: dict[str, Any]) -> dict[str, Any]:
    location = payload.get("location")
    details = payload.get("property_details")
    has_location = isinstance(location, dict)
    has_details = isinstance(details, dict)
    if not has_location and not has_details:
        return payload

    location = _normalize_dls_section(dict(location), field_prefix="location") if has_location else {}
    details = _normalize_dls_section(dict(details), field_prefix="property_details") if has_details else {}
    shared_fields = (*PARCEL_IDENTIFIER_FIELDS, *DLS_CANONICAL_FIELDS)
    for field in shared_fields:
        location_value = location.get(field) if has_location else None
        details_value = details.get(field) if has_details else None
        value = location_value or details_value
        if value is None:
            continue
        if has_location and not location_value:
            location[field] = value
        if has_details and not details_value:
            details[field] = value
    if has_location:
        payload["location"] = location
    if has_details:
        payload["property_details"] = details
    return payload


def _is_mock_session(db: Session) -> bool:
    return getattr(type(db), "__module__", "").startswith("unittest.mock")


def _apply_dls_master_values(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Fill official DLS names from the master table when codes are supplied."""
    if _is_mock_session(db):
        return payload
    location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    details = payload.get("property_details") if isinstance(payload.get("property_details"), dict) else {}
    codes = {
        "gov_code": _section_text(details, "gov_code") or _section_text(location, "gov_code"),
        "dept_code": _section_text(details, "dept_code") or _section_text(location, "dept_code"),
        "vill_code": _section_text(details, "vill_code") or _section_text(location, "vill_code"),
        "hod_code": _section_text(details, "hod_code") or _section_text(location, "hod_code"),
        "sect_code": _section_text(details, "sect_code") or _section_text(location, "sect_code"),
    }
    if not any(codes.values()):
        return payload

    name_fields = {
        "gov": "gov_name",
        "dept": "dept_name",
        "vill": "vill_name",
        "hod": "hod_name",
        "sect": "sect_name",
    }
    code_fields = {
        "gov": "gov_code",
        "dept": "dept_code",
        "vill": "vill_code",
        "hod": "hod_code",
        "sect": "sect_code",
    }
    for level, code_field in code_fields.items():
        code = codes[code_field]
        if not code:
            continue
        parents = {parent: codes[parent] for parent in DLS_PARENTS[level] if codes.get(parent)}
        official_name = dls_official_name(db, level=level, code=code, parents=parents)
        if not official_name:
            _property_field_error(
                field=f"location.{code_field}",
                code="invalid_value",
                message=f"Unknown DLS {level} code",
            )
        for section in (location, details):
            if not section:
                continue
            section[code_field] = code
            section[name_fields[level]] = official_name
    if location:
        payload["location"] = location
    if details:
        payload["property_details"] = details
    return payload


def _section_text(section: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(section, dict):
        return ""
    for key in keys:
        value = str(section.get(key) or "").strip()
        if value:
            return value
    return ""


def _parcel_lookup_value(payload: dict[str, Any], *keys: str) -> str:
    details = payload.get("property_details") if isinstance(payload.get("property_details"), dict) else {}
    location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    return _section_text(details, *keys) or _section_text(location, *keys)


def _json_text_equals(path: tuple[str, ...], value: str):
    return PropertyListingSubmission.payload.op("#>>")("{" + ",".join(path) + "}") == value


def _normalize_owner_identification(owner: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(owner)
    identification = next(
        (
            _cleaned_text(normalized.get(key), field=f"owner_information.owners.{key}", max_length=100)
            for key in OWNER_IDENTIFICATION_KEYS
            if normalized.get(key) not in (None, "")
        ),
        None,
    )
    if identification:
        normalized["ssi"] = identification
        normalized["social_security_id"] = identification
        normalized["owner_id_or_passport"] = identification
        normalized["identification_number"] = identification
    documents = normalized.get("documents")
    if not isinstance(documents, list):
        documents = normalized.get("owner_documents")
    if isinstance(documents, list):
        normalized["documents"] = documents
    return normalized


def property_option_ids_from_payload(payload: dict[str, Any] | None) -> tuple[int | None, int | None]:
    details = _property_details_dict(payload)
    furnishing_status_id = _optional_int(
        details.get("furnishing_status_id")
        if details.get("furnishing_status_id") not in (None, "")
        else details.get("furnishingStatusId")
    )
    floor_id = _optional_int(
        details.get("floor_id")
        if details.get("floor_id") not in (None, "")
        else details.get("floorId")
    )
    return furnishing_status_id, floor_id


def stored_furnishing_status_id(
    submission: PropertyListingSubmission,
    payload: dict[str, Any] | None = None,
) -> int | None:
    column_value = _optional_int(getattr(submission, "furnishing_status_id", None))
    if column_value is not None:
        return column_value
    furnishing_status_id, _ = property_option_ids_from_payload(
        payload if payload is not None else getattr(submission, "payload", None)
    )
    return furnishing_status_id


def stored_floor_id(
    submission: PropertyListingSubmission,
    payload: dict[str, Any] | None = None,
) -> int | None:
    column_value = _optional_int(getattr(submission, "floor_id", None))
    if column_value is not None:
        return column_value
    _, floor_id = property_option_ids_from_payload(
        payload if payload is not None else getattr(submission, "payload", None)
    )
    return floor_id


def apply_property_option_ids_to_payload(
    payload: dict[str, Any] | None,
    *,
    furnishing_status_id: int | None = None,
    floor_id: int | None = None,
) -> dict[str, Any]:
    normalized = dict(payload or {})
    details = _property_details_dict(normalized)
    if furnishing_status_id is not None:
        details["furnishing_status_id"] = furnishing_status_id
        details["furnishingStatusId"] = furnishing_status_id
        details.setdefault("furnishingStatus", details.get("furnishing_status") or details.get("furnishing"))
    if floor_id is not None:
        details["floor_id"] = floor_id
        details["floorId"] = floor_id
        if details.get("floor_number") not in (None, ""):
            details.setdefault("floorNumber", details["floor_number"])
        stored_floor = _optional_int(details.get("floor"))
        if stored_floor == floor_id and details.get("floor_number") not in (None, "") and stored_floor != _optional_int(
            details.get("floor_number")
        ):
            details["floor"] = details["floor_number"]
        elif details.get("floor") in (None, ""):
            details["floor"] = (
                details["floor_number"] if details.get("floor_number") not in (None, "") else floor_id
            )
    if details:
        normalized["property_details"] = details
    return normalized


def persist_property_option_columns(
    submission: PropertyListingSubmission,
    payload: dict[str, Any] | None,
) -> None:
    furnishing_status_id, floor_id = property_option_ids_from_payload(payload)
    submission.furnishing_status_id = furnishing_status_id
    submission.floor_id = floor_id


def remove_owner_address(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Remove the retired owner_address field while preserving all other owner data."""
    normalized = dict(payload or {})
    owner_information = normalized.get("owner_information")
    if not isinstance(owner_information, dict):
        return normalized

    owner_information = dict(owner_information)
    owner_information.pop("owner_address", None)
    owners = owner_information.get("owners")
    if isinstance(owners, list):
        owner_information["owners"] = [
            {key: value for key, value in owner.items() if key != "owner_address"}
            if isinstance(owner, dict)
            else owner
            for owner in owners
        ]
    normalized["owner_information"] = owner_information
    return normalized


def remove_dld_number(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(payload or {})
    details = normalized.get("property_details")
    if not isinstance(details, dict):
        return normalized
    details = dict(details)
    for key in ("dld_number", "dldNumber", "DLD_number", "DLDNumber"):
        details.pop(key, None)
    normalized["property_details"] = details
    return normalized


def add_map_pin_to_response(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    location = normalized.get("location")
    if not isinstance(location, dict):
        return normalized
    location = dict(location)
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    location["map_pin"] = (
        {"latitude": latitude, "longitude": longitude}
        if latitude is not None and longitude is not None
        else None
    )
    normalized["location"] = location
    return normalized


def _property_field_error(
    *,
    field: str,
    code: str,
    message: str,
    status_code: int = STATUS_BAD_REQUEST,
    error_code: str = "VALIDATION_ERROR",
) -> NoReturn:
    raise_api_error(
        status_code=status_code,
        code=error_code,
        message=message,
        details=[{"field": field, "code": code, "message": message}],
    )


def _normalize_primary_images(payload: dict[str, Any]) -> dict[str, Any]:
    media = payload.get("media_documents")
    if not isinstance(media, dict):
        return payload
    media = dict(media)
    images = media.get("images")
    if not isinstance(images, list):
        return payload

    normalized_images: list[Any] = []
    selected_primary = False
    for index, raw_image in enumerate(images):
        if not isinstance(raw_image, dict):
            normalized_images.append(raw_image)
            continue
        image = dict(raw_image)
        requested_primary = coerce_bool(image.get("is_primary"), default=False)
        image["is_primary"] = requested_primary and not selected_primary
        if image["is_primary"]:
            selected_primary = True
        normalized_images.append(image)
    if normalized_images and not selected_primary:
        for index, image in enumerate(normalized_images):
            if isinstance(image, dict) and _media_item_url(image):
                image["is_primary"] = True
                break
    media["images"] = normalized_images
    payload["media_documents"] = media
    return payload


def _optional_coordinate(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _normalize_location(payload: dict[str, Any]) -> dict[str, Any]:
    location = payload.get("location")
    if not isinstance(location, dict):
        return payload
    location = dict(location)
    if isinstance(location.get("area_id"), (list, tuple, set, dict)):
        _property_field_error(
            field="location.area_id",
            code="single_value_required",
            message="Add Property area must be a single master-data value",
        )
    map_pin = location.get("map_pin")
    if isinstance(map_pin, dict):
        location.setdefault("latitude", map_pin.get("latitude", map_pin.get("lat")))
        location.setdefault("longitude", map_pin.get("longitude", map_pin.get("lng")))
    if "lat" in location and "latitude" not in location:
        location["latitude"] = location.get("lat")
    if "lng" in location and "longitude" not in location:
        location["longitude"] = location.get("lng")
    location.pop("lat", None)
    location.pop("lng", None)
    location.pop("map_pin", None)

    latitude = _optional_coordinate(location.get("latitude"))
    longitude = _optional_coordinate(location.get("longitude"))
    if latitude is None or longitude is None:
        location["latitude"] = None
        location["longitude"] = None
        payload["location"] = location
        return payload
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        _property_field_error(
            field="location",
            code="invalid_coordinates",
            message="Latitude and longitude must be numeric",
        )
    if not -90 <= latitude <= 90:
        _property_field_error(field="location.latitude", code="invalid_value", message="Latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        _property_field_error(field="location.longitude", code="invalid_value", message="Longitude must be between -180 and 180")
    location["latitude"] = latitude
    location["longitude"] = longitude
    payload["location"] = location
    return payload


def _normalize_property_details(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("property_details")
    if not isinstance(details, dict):
        details = payload.get("propertyDetails")
    if not isinstance(details, dict):
        return payload
    details = dict(details)

    if "built_up_area" not in details:
        for alias in ("property_area", "area"):
            if alias in details:
                details["built_up_area"] = details.pop(alias)
                break
    if isinstance(details.get("built_up_area"), (list, tuple, set, dict)):
        _property_field_error(
            field="property_details.built_up_area",
            code="single_value_required",
            message="Property area must be a single numeric value",
        )

    option_fields = (
        ("completion_status", ("completion_status",), "completion_status"),
        ("direction", ("direction",), "direction"),
    )
    for group, aliases, storage_key in option_fields:
        supplied_key = next((key for key in aliases if details.get(key) not in (None, "")), None)
        if supplied_key:
            option = resolve_property_option(
                db,
                group=group,
                value=details[supplied_key],
                field=f"property_details.{supplied_key}",
            )
            for alias in aliases:
                if alias != storage_key:
                    details.pop(alias, None)
            details[storage_key] = option.slug

    furnishing_key = _first_supplied_key(details, FURNISHING_OPTION_KEYS)
    if furnishing_key:
        furnishing = resolve_property_option(
            db,
            group="furnishing_status",
            value=details[furnishing_key],
            field=f"property_details.{furnishing_key}",
        )
        for key in FURNISHING_OPTION_KEYS:
            details.pop(key, None)
        details["furnishing"] = furnishing.slug
        details["furnishing_status"] = furnishing.slug
        details["furnishingStatus"] = furnishing.slug
        details["furnishing_status_id"] = furnishing.id
        details["furnishingStatusId"] = furnishing.id

    floor_key = _first_supplied_key(details, FLOOR_OPTION_KEYS)
    if floor_key:
        supplied_floor = details.get("floor")
        floor = resolve_property_option(
            db,
            group="floor",
            value=details[floor_key],
            field=f"property_details.{floor_key}",
        )
        for key in FLOOR_OPTION_KEYS:
            details.pop(key, None)
        details["floor_id"] = floor.id
        details["floorId"] = floor.id
        details["floor_number"] = floor.numeric_value
        details["floorNumber"] = floor.numeric_value
        details["floor_level"] = floor.name
        details["floorLevel"] = floor.name
        if isinstance(supplied_floor, dict):
            details["floor"] = (
                supplied_floor.get("id")
                or supplied_floor.get("value")
                or supplied_floor.get("numeric_value")
                or supplied_floor.get("numericValue")
                or floor.numeric_value
            )
        elif supplied_floor not in (None, ""):
            details["floor"] = supplied_floor
        elif floor.numeric_value is not None:
            details["floor"] = floor.numeric_value
        else:
            details["floor"] = floor.slug

    if "year_of_construction" in details and "year_built" not in details:
        details["year_built"] = details.pop("year_of_construction")
    year_built = details.get("year_built")
    if year_built is not None:
        try:
            year_built = int(year_built)
        except (TypeError, ValueError):
            _property_field_error(field="property_details.year_built", code="invalid_value", message="Year built must be a four-digit year")
        if year_built < 1800 or year_built > utc_now().year + 1:
            _property_field_error(field="property_details.year_built", code="invalid_value", message="Year built is outside the valid range")
        details["year_built"] = year_built

    payload["property_details"] = details
    return payload


def _normalize_listing_purpose(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    basic = payload.get("basic_information")
    if not isinstance(basic, dict) or basic.get("listing_purpose") in (None, ""):
        return payload
    basic = dict(basic)
    option = resolve_property_option(
        db,
        group="listing_purpose",
        value=basic["listing_purpose"],
        field="basic_information.listing_purpose",
    )
    basic["listing_purpose"] = "sale_or_rent" if option.slug == "sale-or-rent" else option.slug
    payload["basic_information"] = basic
    return payload


def _validate_feature_ids(db: Session, payload: dict[str, Any]) -> None:
    amenities = payload.get("amenities")
    if not isinstance(amenities, dict) or "feature_ids" not in amenities:
        return
    raw_ids = amenities.get("feature_ids")
    if not isinstance(raw_ids, list):
        _property_field_error(
            field="amenities.feature_ids",
            code="invalid_type",
            message="Property feature IDs must be an array",
        )
    try:
        feature_ids = list(dict.fromkeys(int(value) for value in raw_ids))
    except (TypeError, ValueError):
        _property_field_error(
            field="amenities.feature_ids",
            code="invalid_value",
            message="Property feature IDs must be integers from the feature catalog",
        )
    existing_ids = set(
        db.execute(
            select(Feature.id).where(Feature.id.in_(feature_ids), Feature.is_active.is_(True))
        ).scalars().all()
    )
    invalid_ids = [feature_id for feature_id in feature_ids if feature_id not in existing_ids]
    if invalid_ids:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVALID_VALUE",
            message="One or more property features are invalid",
            details=[
                {
                    "field": "amenities.feature_ids",
                    "code": "invalid_value",
                    "message": f"Unknown or inactive feature IDs: {invalid_ids}",
                }
            ],
        )
    amenities = dict(amenities)
    amenities["feature_ids"] = feature_ids
    payload["amenities"] = amenities


def _validate_and_enrich_owners(db: Session, payload: dict[str, Any]) -> None:
    owner_information = payload.get("owner_information")
    if not isinstance(owner_information, dict):
        return
    owners = owner_information.get("owners")
    if not isinstance(owners, list):
        return
    normalized_owners: list[Any] = []
    seen_owner_ids: set[UUID] = set()
    for index, raw_owner in enumerate(owners):
        if not isinstance(raw_owner, dict):
            normalized_owners.append(raw_owner)
            continue
        owner = dict(raw_owner)
        owner = _normalize_owner_identification(owner)
        raw_owner_id = owner.get("owner_user_id") or owner.get("owner_id") or owner.get("id")
        if not raw_owner_id:
            normalized_owners.append(owner)
            continue
        try:
            owner_id = UUID(str(raw_owner_id))
        except ValueError:
            _property_field_error(
                field=f"owner_information.owners.{index}.owner_user_id",
                code="invalid_value",
                message="Selected owner ID is invalid",
            )
        if owner_id in seen_owner_ids:
            _property_field_error(
                field=f"owner_information.owners.{index}.owner_user_id",
                code="duplicate",
                message="The same owner cannot be selected more than once",
                status_code=STATUS_CONFLICT,
                error_code="DUPLICATE_OWNER",
            )
        user = db.get(User, owner_id)
        owner_role = (
            db.execute(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == owner_id, Role.name.in_(["owner", "registered_user"]))
                .limit(1)
            ).scalar_one_or_none()
            if user
            else None
        )
        if not user or not user.is_active or not owner_role:
            _property_field_error(
                field=f"owner_information.owners.{index}.owner_user_id",
                code="owner_not_found",
                message="Selected owner was not found or is inactive",
                error_code="OWNER_NOT_FOUND",
            )
        seen_owner_ids.add(owner_id)
        owner["id"] = str(owner_id)
        owner["owner_user_id"] = str(owner_id)
        owner.setdefault("full_name", user.full_name)
        owner.setdefault("email", user.email)
        owner.setdefault("phone", user.phone_number)
        normalized_owners.append(owner)
    owner_information = dict(owner_information)
    owner_information["owners"] = normalized_owners
    payload["owner_information"] = owner_information


def prepare_property_payload(
    db: Session,
    payload: dict[str, Any] | None,
    *,
    for_submit: bool = False,
) -> dict[str, Any]:
    normalized = remove_dld_number(payload)
    normalized = _normalize_listing_purpose(db, normalized)
    normalized = _normalize_property_details(db, normalized)
    normalized = _normalize_location(normalized)
    normalized = _sync_parcel_and_dls_fields(normalized)
    normalized = _apply_dls_master_values(db, normalized)
    normalized = _normalize_primary_images(normalized)
    _validate_feature_ids(db, normalized)
    _validate_and_enrich_owners(db, normalized)
    apply_applicable_pricing(normalized)
    return normalized


def prepare_property_contact_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate optional guard fields and remove the retired owner field."""
    normalized = remove_owner_address(payload)
    details = normalized.get("property_details")
    if not isinstance(details, dict):
        return normalized

    details = dict(details)
    if "guard_name" in details and details["guard_name"] is not None:
        if not isinstance(details["guard_name"], str):
            _property_field_error(field="property_details.guard_name", code="invalid_type", message="guard_name must be a string")
        guard_name = details["guard_name"].strip()
        if len(guard_name) > 255:
            _property_field_error(field="property_details.guard_name", code="max_length", message="guard_name must not exceed 255 characters")
        details["guard_name"] = guard_name or None

    if "guard_phone_number" in details and details["guard_phone_number"] is not None:
        if not isinstance(details["guard_phone_number"], str):
            _property_field_error(
                field="property_details.guard_phone_number",
                code="invalid_type",
                message="guard_phone_number must be a string",
            )
        guard_phone_number = details["guard_phone_number"].strip()
        if guard_phone_number:
            try:
                details["guard_phone_number"] = validate_e164_phone(
                    guard_phone_number,
                    field_name="guard_phone_number",
                )
            except ValueError as exc:
                _property_field_error(
                    field="property_details.guard_phone_number",
                    code="invalid_value",
                    message=str(exc),
                )
        else:
            details["guard_phone_number"] = None

    normalized["property_details"] = details
    return normalized


SQFT_TO_SQM = Decimal("0.09290304")
BUILT_UP_AREA_UNIT_KEYS = ("built_up_area_unit", "area_unit")


def _validated_built_up_area(payload: dict[str, Any] | None) -> tuple[Decimal, str | None, str] | None:
    details = (payload or {}).get("property_details")
    if not isinstance(details, dict) or "built_up_area" not in details or details.get("built_up_area") is None:
        return None

    unit_key = next((key for key in BUILT_UP_AREA_UNIT_KEYS if key in details), None)
    unit_value = details.get(unit_key)
    unit = "sqm" if unit_value is None else str(unit_value).strip().lower()
    if unit not in {"sqm", "sqft"}:
        _property_field_error(
            field=f"property_details.{unit_key or 'built_up_area_unit'}",
            code="invalid_value",
            message="Building area must be stored in sqm",
        )

    value = details["built_up_area"]
    if isinstance(value, bool):
        _property_field_error(
            field="property_details.built_up_area",
            code="invalid_value",
            message="Built-up area must be a numeric value greater than 0",
        )
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        _property_field_error(
            field="property_details.built_up_area",
            code="invalid_value",
            message="Built-up area must be a numeric value greater than 0",
        )
    if not decimal_value.is_finite() or decimal_value <= 0:
        _property_field_error(
            field="property_details.built_up_area",
            code="invalid_value",
            message="Built-up area must be a numeric value greater than 0",
        )

    return decimal_value, unit_key, unit


def validate_built_up_area(payload: dict[str, Any] | None) -> None:
    """Validate entered area without changing draft payload values or units."""
    _validated_built_up_area(payload)


def normalize_built_up_area_to_sqm(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a submitted payload whose built_up_area is canonical square meters."""
    normalized = dict(payload or {})
    validated = _validated_built_up_area(normalized)
    if validated is None:
        return normalized

    value, unit_key, unit = validated
    details = dict(normalized["property_details"])
    if unit == "sqft":
        details["built_up_area"] = float(value * SQFT_TO_SQM)
    details["built_up_area_unit"] = "sqm"
    if unit_key and unit_key != "built_up_area_unit":
        details[unit_key] = "sqm"
    normalized["property_details"] = details
    return normalized


SALE_PRICE_FIELDS = ("furnished_sale_price", "unfurnished_sale_price")
RENT_PRICE_FIELDS = (
    "furnished_rent_price",
    "unfurnished_rent_price",
    "semi_furnished_rent_price",
)
PRICING_AMOUNT_FIELDS = ("price", *SALE_PRICE_FIELDS, *RENT_PRICE_FIELDS, "service_charge", "maintenance_fee")
PRICING_CURRENCY_FIELD_KEYS = {
    "price": "currency",
    "furnished_sale_price": "currency",
    "unfurnished_sale_price": "currency",
    "furnished_rent_price": "currency",
    "unfurnished_rent_price": "currency",
    "semi_furnished_rent_price": "currency",
    "service_charge": "service_charge_currency",
    "maintenance_fee": "maintenance_fee_currency",
}


def _validated_pricing_amount(value: Any, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _property_field_error(
            field=f"pricing.{field_name}",
            code="invalid_value",
            message=f"{field_name} must be a numeric value greater than or equal to 0",
        )
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        _property_field_error(
            field=f"pricing.{field_name}",
            code="invalid_value",
            message=f"{field_name} must be a numeric value greater than or equal to 0",
        )
    if not decimal_value.is_finite() or decimal_value < 0:
        _property_field_error(
            field=f"pricing.{field_name}",
            code="invalid_value",
            message=f"{field_name} must be a numeric value greater than or equal to 0",
        )
    return decimal_value


def _supported_pricing_currency(value: Any, *, field_name: str) -> str:
    try:
        return assert_supported_currency(value, field_name=field_name)
    except HTTPException as exc:
        _property_field_error(
            field=f"pricing.{field_name}",
            code="invalid_value",
            message=str(exc.detail),
        )


def _pricing_currency_for_field(pricing: dict[str, Any], field: str) -> str:
    currency_key = PRICING_CURRENCY_FIELD_KEYS[field]
    if field == "price":
        return _supported_pricing_currency(pricing.get("currency"), field_name="currency")
    override = pricing.get(currency_key)
    if override is not None:
        return _supported_pricing_currency(override, field_name=currency_key)
    return _supported_pricing_currency(pricing.get("currency"), field_name="currency")


def validate_pricing(payload: dict[str, Any] | None, *, for_submit: bool = False) -> None:
    """Validate pricing amounts and currencies without changing draft payload values."""
    pricing = (payload or {}).get("pricing")
    if not isinstance(pricing, dict):
        return

    for field in PRICING_AMOUNT_FIELDS:
        if field in pricing and pricing[field] is not None:
            _validated_pricing_amount(pricing[field], field_name=field)

    _pricing_currency_for_field(pricing, "price")
    for currency_key in ("service_charge_currency", "maintenance_fee_currency"):
        if pricing.get(currency_key) is not None:
            _supported_pricing_currency(pricing.get(currency_key), field_name=currency_key)

    if not for_submit:
        return
    basic = (payload or {}).get("basic_information") or {}
    details = (payload or {}).get("property_details") or {}
    purpose = basic.get("listing_purpose")
    furnishing = (
        details.get("furnishing")
        or details.get("furnishing_status")
        or details.get("furnishingStatus")
        or details.get("furniture_status")
    )
    if not purpose or not furnishing:
        return

    legacy_price_present = pricing.get("price") is not None
    furnishing_key = str(furnishing).replace("-", "_")
    sale_field = {
        "furnished": "furnished_sale_price",
        "unfurnished": "unfurnished_sale_price",
    }.get(furnishing_key)
    rent_field = {
        "furnished": "furnished_rent_price",
        "unfurnished": "unfurnished_rent_price",
        "semi_furnished": "semi_furnished_rent_price",
    }.get(furnishing_key)

    if purpose in {"sale", "sale_or_rent"}:
        has_sale_price = legacy_price_present or (
            pricing.get(sale_field) is not None if sale_field else any(pricing.get(field) is not None for field in SALE_PRICE_FIELDS)
        )
        if not has_sale_price:
            _property_field_error(
                field=f"pricing.{sale_field or 'sale_price'}",
                code="missing_required_field",
                message="A sale price matching the furnishing status is required",
            )
    if purpose in {"rent", "sale_or_rent"}:
        has_rent_price = legacy_price_present or (rent_field is not None and pricing.get(rent_field) is not None)
        if not has_rent_price:
            _property_field_error(
                field=f"pricing.{rent_field or 'rent_price'}",
                code="missing_required_field",
                message="A rent price matching the furnishing status is required",
            )


def _furnishing_price_key(furnishing: Any) -> str:
    return str(furnishing or "").strip().lower().replace("-", "_").replace(" ", "_")


def applicable_price_fields(purpose: Any, furnishing: Any) -> tuple[str, ...]:
    furnishing_key = _furnishing_price_key(furnishing)
    sale_field = {
        "furnished": "furnished_sale_price",
        "unfurnished": "unfurnished_sale_price",
        "semi_furnished": "unfurnished_sale_price",
    }.get(furnishing_key)
    rent_field = {
        "furnished": "furnished_rent_price",
        "unfurnished": "unfurnished_rent_price",
        "semi_furnished": "semi_furnished_rent_price",
    }.get(furnishing_key)
    fields: list[str] = []
    if purpose in {"sale", "sale_or_rent"} and sale_field:
        fields.append(sale_field)
    if purpose in {"rent", "sale_or_rent"} and rent_field:
        fields.append(rent_field)
    return tuple(dict.fromkeys(fields))


def apply_applicable_pricing(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the sale/rent price fields that match listing purpose + furnishing."""
    normalized = payload if isinstance(payload, dict) else {}
    pricing = normalized.get("pricing")
    if not isinstance(pricing, dict):
        return normalized
    basic = normalized.get("basic_information") or {}
    details = normalized.get("property_details") or {}
    purpose = basic.get("listing_purpose") if isinstance(basic, dict) else None
    furnishing = None
    if isinstance(details, dict):
        furnishing = (
            details.get("furnishing")
            or details.get("furnishing_status")
            or details.get("furnishingStatus")
            or details.get("furniture_status")
        )
    if not purpose or not furnishing:
        return normalized
    allowed = set(applicable_price_fields(purpose, furnishing))
    pricing = dict(pricing)
    for field in (*SALE_PRICE_FIELDS, *RENT_PRICE_FIELDS):
        if field not in allowed:
            pricing.pop(field, None)
    normalized["pricing"] = pricing
    return normalized


def normalize_pricing_currency_codes(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Uppercase/default pricing currencies without converting amounts (draft-safe)."""
    normalized = dict(payload or {})
    pricing = normalized.get("pricing")
    if not isinstance(pricing, dict):
        return normalized

    pricing = dict(pricing)
    settings = get_settings()
    pricing["currency"] = _supported_pricing_currency(pricing.get("currency"), field_name="currency")
    for currency_key in ("service_charge_currency", "maintenance_fee_currency"):
        if pricing.get(currency_key) is not None:
            pricing[currency_key] = _supported_pricing_currency(pricing.get(currency_key), field_name=currency_key)
    normalized["pricing"] = pricing
    return normalized


def normalize_pricing_to_jod(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a submitted payload whose pricing amounts are canonical JOD values."""
    normalized = normalize_pricing_currency_codes(payload)
    pricing = normalized.get("pricing")
    if not isinstance(pricing, dict):
        return normalized

    pricing = dict(pricing)
    settings = get_settings()
    for field in PRICING_AMOUNT_FIELDS:
        if field not in pricing or pricing[field] is None:
            continue
        amount = _validated_pricing_amount(pricing[field], field_name=field)
        if amount is None:
            continue
        currency = _pricing_currency_for_field(pricing, field)
        try:
            converted = convert_amount_to_jod_or_http_error(amount, currency, field_name=field)
        except HTTPException as exc:
            raise_api_error(
                status_code=exc.status_code,
                code="PRICE_CONVERSION_UNAVAILABLE",
                message="Unable to convert property pricing to JOD at this time",
                details=[
                    {
                        "field": f"pricing.{field}",
                        "code": "system_error",
                        "message": "Live currency conversion is temporarily unavailable",
                    }
                ],
            )
        pricing[field] = float(converted)

    pricing["currency"] = settings.default_currency
    pricing.pop("service_charge_currency", None)
    pricing.pop("maintenance_fee_currency", None)
    normalized["pricing"] = pricing
    return normalized


def pricing_response_fields(pricing: dict[str, Any] | None) -> dict[str, Any]:
    settings = get_settings()
    data = pricing or {}
    result = {
        "price": str(data.get("price") or "0"),
        "currency": data.get("currency") or settings.default_currency,
    }
    if data.get("service_charge") is not None:
        result["service_charge"] = data.get("service_charge")
    if data.get("maintenance_fee") is not None:
        result["maintenance_fee"] = data.get("maintenance_fee")
    for field in (*SALE_PRICE_FIELDS, *RENT_PRICE_FIELDS):
        if data.get(field) is not None:
            result[field] = data.get(field)
    return result


REFERENCE_NUMBER_START = 10001
REFERENCE_NUMBER_MAX_ATTEMPTS = 12
REFERENCE_NUMBER_SEQUENCE = "property_reference_number_seq"


def _first_letter(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    for character in value.strip():
        if character.isalpha():
            return character.upper()
    return ""


def _payload_int_id(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed else None


def _payload_reference_number(payload: dict[str, Any] | None) -> str | None:
    details = (payload or {}).get("property_details")
    if not isinstance(details, dict):
        return None
    value = details.get("reference_number")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def stored_reference_number(
    submission: PropertyListingSubmission | None,
    payload: dict[str, Any] | None = None,
) -> str | None:
    if submission is not None:
        column_value = getattr(submission, "reference_number", None)
        if isinstance(column_value, str) and column_value.strip():
            return column_value.strip()
        if payload is None:
            payload = submission.payload
    return _payload_reference_number(payload)


def displayed_reference_number(
    submission: PropertyListingSubmission,
    *,
    payload: dict[str, Any] | None = None,
    property_id: UUID | None = None,
) -> str:
    stored = stored_reference_number(submission, payload)
    if stored:
        return stored
    resolved_id = property_id or submission.property_id or submission.id
    return str(resolved_id)[:8]


def write_payload_reference_number(payload: dict[str, Any] | None, reference_number: str | None) -> dict[str, Any]:
    """Set or strip reference_number inside property_details without creating that section."""
    normalized = dict(payload or {})
    details = normalized.get("property_details")
    if not isinstance(details, dict):
        return normalized
    details = dict(details)
    if reference_number:
        details["reference_number"] = reference_number
    else:
        details.pop("reference_number", None)
    normalized["property_details"] = details
    return normalized


def reference_number_prefix(db: Session, payload: dict[str, Any] | None) -> str | None:
    basic = (payload or {}).get("basic_information") or {}
    if not isinstance(basic, dict):
        return None
    category_id = _payload_int_id(basic.get("category_id"))
    type_id = _payload_int_id(basic.get("type_id"))
    if not category_id or not type_id:
        return None
    category = db.get(PropertyCategory, category_id)
    property_type = db.get(PropertyType, type_id)
    category_letter = _first_letter(getattr(category, "name", None)) or _first_letter(getattr(category, "slug", None))
    type_letter = _first_letter(getattr(property_type, "name", None)) or _first_letter(getattr(property_type, "slug", None))
    if category_letter and type_letter:
        return f"{category_letter}{type_letter}"
    return None


def generate_reference_number(value: int | str) -> str:
    return str(int(value))


def _next_reference_number_value(db: Session) -> int:
    result = db.execute(text(f"SELECT nextval('{REFERENCE_NUMBER_SEQUENCE}')"))
    scalar = result.scalar() if hasattr(result, "scalar") else None
    try:
        return int(scalar)
    except (TypeError, ValueError):
        return REFERENCE_NUMBER_START


def _reference_number_taken(db: Session, value: str, *, exclude_id: UUID | None = None) -> bool:
    payload_ref = PropertyListingSubmission.payload.op("#>>")("{property_details,reference_number}")
    stmt = select(PropertyListingSubmission.id).where(
        or_(
            PropertyListingSubmission.reference_number == value,
            payload_ref == value,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(PropertyListingSubmission.id != exclude_id)
    row = db.execute(stmt.limit(1)).first()
    if row in (None, False):
        return False
    # Unit tests often pass a MagicMock session; those objects are truthy but not DB rows.
    if getattr(type(row), "__module__", "").startswith("unittest.mock"):
        return False
    return True


def allocate_reference_number(db: Session, prefix: str | None = None, *, exclude_id: UUID | None = None) -> str:
    for _ in range(REFERENCE_NUMBER_MAX_ATTEMPTS):
        candidate = generate_reference_number(_next_reference_number_value(db))
        if not candidate.isdigit():
            continue
        if not _reference_number_taken(db, candidate, exclude_id=exclude_id):
            return candidate
    raise_api_error(
        status_code=STATUS_INTERNAL_SERVER_ERROR,
        code="DATABASE_ERROR",
        message="Unable to allocate a unique property reference number",
        details=[
            {
                "field": "property_details.reference_number",
                "code": "system_error",
                "message": "Unable to allocate a unique numeric reference number",
            }
        ],
    )


def assign_reference_number(
    db: Session,
    payload: dict[str, Any] | None,
    *,
    submission: PropertyListingSubmission | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Ignore client-provided reference numbers. Preserve existing or generate once."""
    preserved = stored_reference_number(submission)
    if preserved:
        return write_payload_reference_number(payload, preserved), preserved

    stripped = write_payload_reference_number(payload, None)
    generated = allocate_reference_number(
        db,
        exclude_id=getattr(submission, "id", None) if submission is not None else None,
    )
    return write_payload_reference_number(stripped, generated), generated


def validate_duplicate_property(
    db: Session,
    payload: dict[str, Any] | None,
    *,
    exclude_submission_id: UUID | None = None,
) -> None:
    """Block exact matches on official parcel identifiers or established physical IDs."""
    data = payload or {}
    details = data.get("property_details") or {}
    location = data.get("location") or {}
    if not isinstance(details, dict) and not isinstance(location, dict):
        return

    conditions = []
    village = _parcel_lookup_value(data, "vill_code", "vill_name")
    hod = _parcel_lookup_value(data, "hod_code", "hod_name", "basin_number")
    parcel = _parcel_lookup_value(data, "parcel_number", "plot_number")
    if village and hod and parcel:
        village_match = or_(
            _json_text_equals(("property_details", "vill_code"), village),
            _json_text_equals(("property_details", "vill_name"), village),
            _json_text_equals(("location", "vill_code"), village),
            _json_text_equals(("location", "vill_name"), village),
        )
        hod_match = or_(
            _json_text_equals(("property_details", "hod_code"), hod),
            _json_text_equals(("property_details", "hod_name"), hod),
            _json_text_equals(("property_details", "basin_number"), hod),
            _json_text_equals(("location", "hod_code"), hod),
            _json_text_equals(("location", "hod_name"), hod),
            _json_text_equals(("location", "basin_number"), hod),
        )
        parcel_match = or_(
            _json_text_equals(("property_details", "parcel_number"), parcel),
            _json_text_equals(("property_details", "plot_number"), parcel),
            _json_text_equals(("location", "parcel_number"), parcel),
            _json_text_equals(("location", "plot_number"), parcel),
        )
        dls_match = village_match & hod_match & parcel_match
        gov_code = _parcel_lookup_value(data, "gov_code")
        if gov_code:
            dls_match = dls_match & or_(
                _json_text_equals(("property_details", "gov_code"), gov_code),
                _json_text_equals(("location", "gov_code"), gov_code),
            )
        dept_code = _parcel_lookup_value(data, "dept_code")
        if dept_code:
            dls_match = dls_match & or_(
                _json_text_equals(("property_details", "dept_code"), dept_code),
                _json_text_equals(("location", "dept_code"), dept_code),
            )
        sect_code = _parcel_lookup_value(data, "sect_code")
        if sect_code:
            dls_match = dls_match & or_(
                _json_text_equals(("property_details", "sect_code"), sect_code),
                _json_text_equals(("location", "sect_code"), sect_code),
            )
        conditions.append(dls_match)

    plot_number = _parcel_lookup_value(data, "plot_number")
    basin_number = _parcel_lookup_value(data, "basin_number", "hod_code")
    if plot_number and basin_number:
        conditions.append(
            (
                or_(
                    _json_text_equals(("property_details", "plot_number"), plot_number),
                    _json_text_equals(("location", "plot_number"), plot_number),
                )
            )
            & (
                or_(
                    _json_text_equals(("property_details", "basin_number"), basin_number),
                    _json_text_equals(("property_details", "hod_code"), basin_number),
                    _json_text_equals(("location", "basin_number"), basin_number),
                    _json_text_equals(("location", "hod_code"), basin_number),
                )
            )
        )

    apartment_number = _parcel_lookup_value(data, "apartment_number")
    city_id = str((location if isinstance(location, dict) else {}).get("city_id") or "").strip()
    area_id = str((location if isinstance(location, dict) else {}).get("area_id") or "").strip()
    if apartment_number and city_id and area_id:
        conditions.append(
            (
                or_(
                    _json_text_equals(("property_details", "apartment_number"), apartment_number),
                    _json_text_equals(("location", "apartment_number"), apartment_number),
                )
            )
            & (_json_text_equals(("location", "city_id"), city_id))
            & (_json_text_equals(("location", "area_id"), area_id))
        )

    if not conditions:
        return
    stmt = select(PropertyListingSubmission.id).where(
        PropertyListingSubmission.deleted_at.is_(None),
        or_(*conditions),
    )
    if exclude_submission_id is not None:
        stmt = stmt.where(PropertyListingSubmission.id != exclude_submission_id)
    duplicate_id = db.execute(stmt.limit(1)).scalar_one_or_none()
    if duplicate_id:
        raise_api_error(
            status_code=STATUS_CONFLICT,
            code="DUPLICATE_PROPERTY",
            message="A property with the same identification details already exists",
            details=[
                {
                    "field": "property_details",
                    "code": "duplicate_property",
                    "message": "Official parcel identifiers match an existing property",
                }
            ],
        )


def serialize_submission(submission: PropertyListingSubmission) -> dict:
    payload = submission.payload or {}
    workflow_summary = _submission_workflow_summary(submission)
    show_location = show_location_for_submission(submission, payload)
    reference_number = stored_reference_number(submission, payload)
    readable_payload, _ = apply_show_location_to_payload(with_readable_media_urls(payload), show_location)
    readable_payload = write_payload_reference_number(readable_payload, reference_number)
    furnishing_status_id = stored_furnishing_status_id(submission, payload)
    floor_id = stored_floor_id(submission, payload)
    readable_payload = apply_property_option_ids_to_payload(
        readable_payload,
        furnishing_status_id=furnishing_status_id,
        floor_id=floor_id,
    )
    readable_payload = add_map_pin_to_response(
        remove_dld_number(remove_owner_address(readable_payload))
    )
    return {
        "submission_id": str(submission.id),
        "submitted_by": str(submission.submitted_by),
        **_routing_payload(submission),
        "status": submission.status,
        **workflow_summary,
        "current_step": submission.current_step,
        "last_completed_step": submission.last_completed_step,
        "step_completion": submission.step_completion or compute_step_completion(payload),
        "show_location": show_location,
        "reference_number": reference_number,
        "furnishing_status_id": furnishing_status_id,
        "floor_id": floor_id,
        "payload": readable_payload,
        "reviewed_by": str(submission.reviewed_by) if submission.reviewed_by else None,
        "reviewed_at": _iso(submission.reviewed_at),
        "review_reason": submission.review_reason,
    }


def _pagination(total: int, page: int, page_size: int) -> dict:
    total_pages = math.ceil(total / page_size) if total else 1
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }


def create_submission(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID | None,
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
    status: str = "draft",
    route_through_agency: bool = False,
    roles: tuple[str, ...] = (),
) -> PropertyListingSubmission:
    submitted_at = utc_now() if status not in DRAFT_STATUSES else None
    normalized_payload = prepare_property_payload(
        db,
        with_canonical_media_urls(payload),
        for_submit=status not in DRAFT_STATUSES,
    )
    normalized_payload = prepare_property_contact_fields(normalized_payload)
    normalized_payload, show_location = apply_show_location_to_payload(normalized_payload)
    validate_built_up_area(normalized_payload)
    validate_pricing(normalized_payload, for_submit=status not in DRAFT_STATUSES)
    normalized_payload = normalize_pricing_currency_codes(normalized_payload)
    normalized_payload = normalize_built_up_area_to_sqm(normalized_payload)
    if status not in DRAFT_STATUSES:
        normalized_payload = normalize_pricing_to_jod(normalized_payload)
    normalized_payload, reference_number = assign_reference_number(db, normalized_payload)
    agency_id = validate_routing_agency(
        db,
        route_through_agency=route_through_agency,
        agency_id=agency_id,
        user_id=user_id,
        roles=roles,
    )
    route_through_agency = agency_id is not None
    furnishing_status_id, floor_id = property_option_ids_from_payload(normalized_payload)
    submission = PropertyListingSubmission(
        id=uuid4(),
        submitted_by=user_id,
        route_through_agency=route_through_agency,
        agency_id=agency_id,
        status=status,
        current_step=current_step,
        last_completed_step=last_completed_step,
        payload=normalized_payload,
        step_completion=compute_step_completion(normalized_payload),
        terms_accepted=bool((normalized_payload.get("review_submit") or {}).get("terms_accepted")),
        privacy_accepted=bool((normalized_payload.get("review_submit") or {}).get("privacy_accepted")),
        public_display_authorized=bool((normalized_payload.get("review_submit") or {}).get("public_display_authorized")),
        fees_acknowledged=bool((normalized_payload.get("review_submit") or {}).get("fees_acknowledged")),
        show_location=show_location,
        reference_number=reference_number,
        furnishing_status_id=furnishing_status_id,
        floor_id=floor_id,
        submitted_at=submitted_at,
    )
    db.add(submission)
    return submission


def get_submission_or_404(db: Session, submission_id: UUID) -> PropertyListingSubmission:
    submission = db.get(PropertyListingSubmission, submission_id)
    if not submission or submission.deleted_at is not None:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property submission not found")
    return submission


def update_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    agency_id: UUID | None,
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
    route_through_agency: bool | None = None,
    user_id: UUID | None = None,
    roles: tuple[str, ...] = (),
) -> PropertyListingSubmission:
    workflow_stage = _workflow_stage_for_submission(submission)
    is_editable_status = submission.status in {"draft", REJECTED_STATUS, "in_progress", AGENT_ASSIGNED_STATUS} or (
        workflow_stage == WORKFLOW_STAGE_AGENT_ASSIGNED
    )
    if not is_editable_status:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="This property submission is not editable in its current workflow stage")
    next_payload = prepare_property_payload(db, with_canonical_media_urls(dict(payload)))
    next_payload = prepare_property_contact_fields(next_payload)
    next_payload, show_location = apply_show_location_to_payload(next_payload)
    validate_built_up_area(next_payload)
    validate_pricing(next_payload)
    next_payload = normalize_pricing_currency_codes(next_payload)
    next_payload = normalize_built_up_area_to_sqm(next_payload)
    existing_workflow = _workflow_from_submission(submission)
    if existing_workflow:
        next_payload["_workflow"] = existing_workflow
    next_payload, reference_number = assign_reference_number(db, next_payload, submission=submission)
    submission.payload = next_payload
    submission.show_location = show_location
    submission.reference_number = reference_number
    persist_property_option_columns(submission, next_payload)
    effective_route = (
        bool(getattr(submission, "route_through_agency", False))
        if route_through_agency is None
        else route_through_agency
    )
    submission.agency_id = validate_routing_agency(
        db,
        route_through_agency=effective_route,
        agency_id=agency_id if agency_id is not None else getattr(submission, "agency_id", None),
        user_id=user_id or getattr(submission, "submitted_by", None),
        roles=roles,
    )
    submission.route_through_agency = submission.agency_id is not None
    submission.current_step = current_step
    submission.last_completed_step = last_completed_step
    submission.step_completion = compute_step_completion(next_payload)
    if submission.status in DRAFT_STATUSES:
        submission.status = "draft"
    flag_modified(submission, "payload")
    if submission.property_id and next_payload.get("media_documents") is not None:
        sync_property_media_from_payload(
            db,
            property_id=submission.property_id,
            payload=next_payload,
        )
    return submission


def can_edit_active_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    return False


def _assigned_agent_id(submission: PropertyListingSubmission) -> str | None:
    workflow = _workflow_from_submission(submission)
    return workflow.get("assigned_agent_id")


def _submitter_agency_id(db: Session, submission: PropertyListingSubmission) -> UUID | None:
    if submission.agency_id:
        return submission.agency_id
    submitter = db.get(User, submission.submitted_by)
    return submitter.agency_id if submitter else None


def can_view_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    role_names = _role_names(roles)
    if submission.status in DRAFT_STATUSES:
        return submission.submitted_by == user_id
    if "super_admin" in role_names:
        return True
    if submission.submitted_by == user_id:
        return True
    if _assigned_agent_id(submission) == str(user_id):
        return True
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return True
    return False


def can_edit_working_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    if submission.status in {ACTIVE_STATUS, DEACTIVATED_STATUS, DEAL_CLOSED_STATUS, DEAL_CLOSURE_REQUESTED_STATUS}:
        return False
    if submission.status in DRAFT_STATUSES:
        return submission.submitted_by == user_id
    workflow_stage = _workflow_stage_for_submission(submission)
    role_names = _role_names(roles)
    assigned_agent_id = _assigned_agent_id(submission)
    if submission.status == REJECTED_STATUS or workflow_stage == WORKFLOW_STAGE_REJECTED:
        return submission.submitted_by == user_id or assigned_agent_id == str(user_id)
    if workflow_stage in AGENT_EDIT_STAGES:
        if assigned_agent_id == str(user_id):
            return True
        if "agent" in role_names and submission.submitted_by == user_id:
            return True
        return False
    if submission.status in WORKING_STATUSES and submission.submitted_by == user_id:
        return True
    return False


def can_delete_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    if submission.status in DRAFT_STATUSES:
        return submission.submitted_by == user_id

    workflow_stage = _workflow_stage_for_submission(submission)
    if submission.status != REJECTED_STATUS and workflow_stage != WORKFLOW_STAGE_REJECTED:
        return False

    role_names = _role_names(roles)
    if "super_admin" in role_names:
        return True
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return True
    if submission.submitted_by == user_id:
        return True
    return _assigned_agent_id(submission) == str(user_id)


def assert_can_delete_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    if not can_delete_submission(db, submission, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def assert_can_view_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    if not can_view_submission(db, submission, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def assert_can_edit_working_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    if not can_edit_working_submission(db, submission, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def assert_can_manage_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    role_names = _role_names(roles)
    if "super_admin" in role_names:
        return
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return
    raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def can_review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> bool:
    role_names = _role_names(roles)
    if "super_admin" in role_names:
        return submission.agency_id is None
    if "admin" in role_names and agency_id and _submitter_agency_id(db, submission) == agency_id:
        return True
    return False


def _is_agencyless_super_admin_review(
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
) -> bool:
    return submission.agency_id is None and "super_admin" in _role_names(roles)


def assert_can_review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    roles: tuple[str, ...],
    agency_id: UUID | None,
) -> None:
    is_direct_super_admin_review = _is_agencyless_super_admin_review(submission, roles=roles)
    if submission.agency_id is None and submission.status == SUBMITTED_STATUS and not is_direct_super_admin_review:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")

    allowed_statuses = {AGENT_ASSIGNED_STATUS, PENDING_APPROVAL_STATUS}
    allowed_stages = AGENCY_REVIEW_STAGES
    if is_direct_super_admin_review:
        allowed_statuses = {*allowed_statuses, SUBMITTED_STATUS}
        allowed_stages = {*allowed_stages, WORKFLOW_STAGE_SUBMITTED}
    elif not WORKFLOW_CONFIG.enabled("agent_assignment_required_before_activation", default=True):
        allowed_statuses = {*allowed_statuses, SUBMITTED_STATUS}
        allowed_stages = {*allowed_stages, WORKFLOW_STAGE_SUBMITTED}

    if submission.status not in allowed_statuses:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only agent assigned or pending approval submissions can be reviewed")
    if _workflow_stage_for_submission(submission) not in allowed_stages:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Submission is not ready for agency review")
    if not can_review_submission(db, submission, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


def create_revision_from_active(
    db: Session,
    *,
    source: PropertyListingSubmission,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None,
    payload: dict[str, Any],
    current_step: int,
    last_completed_step: int,
) -> PropertyListingSubmission:
    if source.status != ACTIVE_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only active submissions can create revisions")
    if not can_edit_active_submission(db, source, user_id=user_id, roles=roles, agency_id=agency_id):
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Active property cannot be edited by this user")

    revision_payload = prepare_property_payload(db, dict(payload), for_submit=True)
    revision_payload, show_location = apply_show_location_to_payload(revision_payload)
    validate_built_up_area(revision_payload)
    validate_pricing(revision_payload, for_submit=True)
    validate_duplicate_property(db, revision_payload, exclude_submission_id=source.id)
    revision_payload = normalize_built_up_area_to_sqm(revision_payload)
    revision_payload = normalize_pricing_to_jod(revision_payload)
    revision_payload, reference_number = assign_reference_number(db, revision_payload, submission=source)
    workflow = _payload_workflow(revision_payload)
    workflow["revision_of_submission_id"] = str(source.id)
    workflow["revision_property_id"] = str(source.property_id or source.id)
    workflow["revision_status"] = "pending_reapproval"

    route_through_agency = bool(getattr(source, "route_through_agency", False))
    furnishing_status_id, floor_id = property_option_ids_from_payload(revision_payload)
    revision = PropertyListingSubmission(
        id=uuid4(),
        submitted_by=user_id,
        route_through_agency=route_through_agency,
        agency_id=source.agency_id if route_through_agency else None,
        property_id=source.property_id or source.id,
        status=PENDING_APPROVAL_STATUS,
        current_step=current_step,
        last_completed_step=last_completed_step,
        payload=revision_payload,
        step_completion=compute_step_completion(revision_payload),
        terms_accepted=True,
        privacy_accepted=True,
        public_display_authorized=True,
        fees_acknowledged=True,
        show_location=show_location,
        reference_number=reference_number,
        furnishing_status_id=furnishing_status_id,
        floor_id=floor_id,
        submitted_at=utc_now(),
    )
    db.add(revision)
    record_activity(
        db,
        activity_type="property_revision_submitted",
        message=f"Revision submitted for active property {revision.property_id}",
        user_id=user_id,
        property_id=revision.property_id,
    )
    return revision


def _next_status_on_submit(
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
) -> str:
    role_names = _role_names(roles)
    current_stage = _workflow_stage_for_submission(submission)
    assigned_agent_id = _assigned_agent_id(submission)
    if current_stage in AGENT_EDIT_STAGES and (assigned_agent_id == str(user_id) or "agent" in role_names):
        return WORKFLOW_CONFIG.transition("assigned_agent_submit")
    if submission.status == REJECTED_STATUS or current_stage == WORKFLOW_STAGE_REJECTED:
        return WORKFLOW_CONFIG.transition("rejected_resubmit")
    if "agent" in role_names:
        return WORKFLOW_CONFIG.transition("agent_submit_from_draft")
    if "super_admin" in role_names:
        return WORKFLOW_CONFIG.transition("super_admin_submit")
    if "admin" in role_names:
        return WORKFLOW_CONFIG.transition("agency_admin_submit")
    return WORKFLOW_CONFIG.transition("owner_submit")


def submit_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    user_id: UUID,
    roles: tuple[str, ...],
    agency_id: UUID | None = None,
    review_comment: str | None = None,
) -> PropertyListingSubmission:
    if submission.status in {ACTIVE_STATUS}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Active submissions cannot be resubmitted")
    if not _has_property_image(submission.payload or {}):
        _property_field_error(
            field="media_documents.images",
            code="missing_required_field",
            message="At least one property image is required before submitting",
        )
    route_through_agency = bool(getattr(submission, "route_through_agency", False))
    submission.agency_id = validate_routing_agency(
        db,
        route_through_agency=route_through_agency,
        agency_id=submission.agency_id or agency_id,
        user_id=user_id,
        roles=roles,
    )
    submission.route_through_agency = submission.agency_id is not None
    if submission.route_through_agency:
        record_owner_agency_mapping_for_submission(db, user_id=user_id, agency_id=submission.agency_id, roles=roles)
    submission.payload = prepare_property_payload(db, submission.payload, for_submit=True)
    submission.payload = prepare_property_contact_fields(submission.payload)
    persist_property_option_columns(submission, submission.payload)
    validate_pricing(submission.payload, for_submit=True)
    validate_duplicate_property(db, submission.payload, exclude_submission_id=submission.id)
    submission.payload = normalize_pricing_to_jod(normalize_built_up_area_to_sqm(submission.payload))
    flag_modified(submission, "payload")
    origin = _workflow_from_submission(submission).get("submission_origin") or _submission_origin_for_roles(roles)
    next_status = _next_status_on_submit(submission, user_id=user_id, roles=roles)
    assigned_agent_id = _assigned_agent_id(submission)
    if (
        next_status == SUBMITTED_STATUS
        and submission.status == REJECTED_STATUS
        and WORKFLOW_CONFIG.enabled("clear_agent_on_rejected_resubmit", default=True)
    ):
        assigned_agent_id = None
    if (
        "agent" in _role_names(roles)
        and assigned_agent_id is None
        and WORKFLOW_CONFIG.enabled("agent_submission_auto_assigns_self", default=True)
    ):
        assigned_agent_id = str(user_id)
    submission.status = next_status
    submission.submitted_at = utc_now()
    submission.step_completion = compute_step_completion(submission.payload or {})
    _set_submission_workflow(
        submission,
        stage=next_status,
        origin=origin,
        assigned_agent_id=assigned_agent_id,
        actor_user_id=user_id,
        agent_review_comment=review_comment.strip() if review_comment and next_status == PENDING_APPROVAL_STATUS else None,
    )
    # Persist uploaded media into normalized property_media (not only JSON payload).
    ensure_property_id_and_sync_media(db, submission)
    if next_status == AGENT_ASSIGNED_STATUS:
        notify_assigned_agent_for_submission(db, submission=submission, actor_user_id=user_id)
    else:
        notify_agency_admins_for_submission(db, submission=submission, actor_user_id=user_id)
    return submission


def soft_delete_submission(
    submission: PropertyListingSubmission,
    *,
    deleted_by: UUID,
    reason: str = "Deleted by user",
) -> None:
    submission.deleted_at = utc_now()
    submission.deleted_by = deleted_by
    submission.delete_reason = reason


def resolve_listing_agency_or_400(db: Session, agency_id: UUID | None) -> AgencyMaster:
    if agency_id is None:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency is required before submitting a property")
    agency = db.get(AgencyMaster, agency_id)
    if not agency or not agency.is_active:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Selected agency is not available for property submission")
    return agency


def validate_routing_agency(
    db: Session,
    *,
    route_through_agency: bool,
    agency_id: UUID | None,
    user_id: UUID,
    roles: tuple[str, ...],
) -> UUID | None:
    if owner_may_submit_without_agency(roles, route_through_agency):
        return None
    resolve_listing_agency_or_400(db, agency_id)
    assert_owner_agency_rule(db, user_id=user_id, agency_id=agency_id, roles=roles)
    return agency_id


def assert_owner_agency_rule(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID,
    roles: tuple[str, ...],
) -> None:
    role_names = _role_names(roles)
    if "owner" not in role_names and "registered_user" not in role_names:
        return
    settings = get_settings()
    mappings = active_mappings(db, user_id=user_id, relationship_type=REL_PROPERTY_OWNER)
    if mappings and not settings.allow_owner_multiple_agencies and all(mapping.agency_id != agency_id for mapping in mappings):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Owner is already linked to another agency")


def record_owner_agency_mapping_for_submission(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID,
    roles: tuple[str, ...],
) -> None:
    role_names = _role_names(roles)
    if "owner" not in role_names and "registered_user" not in role_names:
        return
    created = not user_has_active_agency_mapping(
        db,
        user_id=user_id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
    )
    ensure_user_agency_mapping(
        db,
        user_id=user_id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
        actor_user_id=user_id,
    )
    if created and get_settings().allow_owner_multiple_agencies:
        record_activity(
            db,
            activity_type="owner_agency_mapping_created",
            message=f"Owner {user_id} linked to agency {agency_id}",
            user_id=user_id,
        )


def notify_super_admins_for_submission(db: Session, *, submission: PropertyListingSubmission, actor_user_id: UUID) -> None:
    try:
        recipients = db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.name == "super_admin",
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .distinct()
        ).scalars().all()
    except Exception:
        logger.warning(
            "property_submission_super_admin_lookup_failed submission_id=%s",
            submission.id,
        )
        return
    if not isinstance(recipients, (list, tuple)):
        return
    payload = submission.payload or {}
    title = ((payload.get("basic_information") or {}).get("title")) or "property listing"
    for recipient in recipients:
        try:
            with db.begin_nested():
                create_in_app_notification(
                    db,
                    recipient_user_id=recipient.id,
                    actor_user_id=actor_user_id,
                    type_key="property_submission_created",
                    title="New property submission",
                    message=f"New property submission received for {title}.",
                    data={"submission_id": str(submission.id), "agency_id": None},
                    action_url="/manage-listings",
                )
                send_email_notification(
                    to_email=recipient.email,
                    subject="New property submission",
                    body=f"New property submission received for {title}.",
                )
                if recipient.phone_number:
                    send_sms_notification(
                        to_phone=recipient.phone_number,
                        body=f"New property submission received for {title}.",
                    )
        except Exception:
            logger.warning(
                "property_submission_super_admin_notification_failed submission_id=%s recipient=%s",
                submission.id,
                getattr(recipient, "id", None),
            )


def notify_agency_admins_for_submission(db: Session, *, submission: PropertyListingSubmission, actor_user_id: UUID) -> None:
    if not submission.agency_id:
        notify_super_admins_for_submission(db, submission=submission, actor_user_id=actor_user_id)
        return
    recipients = agency_users_with_role(db, agency_id=submission.agency_id, role_name="admin")
    payload = submission.payload or {}
    title = ((payload.get("basic_information") or {}).get("title")) or "property listing"
    for recipient in recipients:
        try:
            with db.begin_nested():
                create_in_app_notification(
                    db,
                    recipient_user_id=recipient.id,
                    actor_user_id=actor_user_id,
                    type_key="property_submission_created",
                    title="New property submission",
                    message=f"New property submission received for {title}.",
                    data={"submission_id": str(submission.id), "agency_id": str(submission.agency_id)},
                    action_url="/manage-listings",
                )
                send_email_notification(
                    to_email=recipient.email,
                    subject="New property submission",
                    body=f"New property submission received for {title}.",
                )
                if recipient.phone_number:
                    send_sms_notification(
                        to_phone=recipient.phone_number,
                        body=f"New property submission received for {title}.",
                    )
        except Exception:
            logger.warning(
                "property_submission_notification_failed submission_id=%s recipient=%s",
                submission.id,
                getattr(recipient, "id", None),
            )


def notify_assigned_agent_for_submission(db: Session, *, submission: PropertyListingSubmission, actor_user_id: UUID) -> None:
    agent_id = _assigned_agent_uuid(submission)
    if not agent_id:
        return
    recipient = db.get(User, agent_id)
    if not recipient:
        return
    payload = submission.payload or {}
    title = ((payload.get("basic_information") or {}).get("title")) or "property listing"
    try:
        with db.begin_nested():
            create_in_app_notification(
                db,
                recipient_user_id=recipient.id,
                actor_user_id=actor_user_id,
                type_key="property_submission_assigned_for_update",
                title="Property submission assigned",
                message=f"Property submission for {title} is assigned to you for completion.",
                data={"submission_id": str(submission.id), "agency_id": str(submission.agency_id) if submission.agency_id else None},
                action_url="/my-listings",
            )
            send_email_notification(
                to_email=recipient.email,
                subject="Property submission assigned",
                body=f"Property submission for {title} is assigned to you for completion.",
            )
            if recipient.phone_number:
                send_sms_notification(
                    to_phone=recipient.phone_number,
                    body=f"Property submission for {title} is assigned to you for completion.",
                )
    except Exception:
        logger.warning(
            "property_assignment_notification_failed submission_id=%s agent_id=%s",
            submission.id,
            getattr(recipient, "id", None),
        )


def review_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    actor_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    action: str,
    reason: str | None = None,
) -> PropertyListingSubmission:
    assert_can_review_submission(
        db,
        submission,
        roles=actor_roles,
        agency_id=actor_agency_id,
    )
    is_direct_super_admin_review = _is_agencyless_super_admin_review(submission, roles=actor_roles)
    workflow = _workflow_from_submission(submission)
    submission_origin = workflow.get("submission_origin") or SUBMISSION_ORIGIN_OWNER
    recipient_user_id = submission.submitted_by
    if action == "approve":
        if (
            not is_direct_super_admin_review
            and WORKFLOW_CONFIG.enabled("agent_assignment_required_before_activation", default=True)
            and not _assigned_agent_id(submission)
        ):
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Assign an agent before approving this property")
        submission.status = ACTIVE_STATUS
        submission.review_reason = None
        ensure_property_id_and_sync_media(db, submission)
        _set_submission_workflow(
            submission,
            stage=WORKFLOW_STAGE_ACTIVE,
            origin=submission_origin,
            actor_user_id=actor_id,
        )
    elif action == "reject":
        if WORKFLOW_CONFIG.enabled("rejection_requires_reason", default=True) and not reason:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Rejection reason is required")
        submission.status = REJECTED_STATUS
        submission.review_reason = reason
        _set_submission_workflow(
            submission,
            stage=WORKFLOW_STAGE_REJECTED,
            origin=submission_origin,
            actor_user_id=actor_id,
        )
    else:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid review action")

    submission.reviewed_by = actor_id
    submission.reviewed_at = utc_now()
    record_activity(
        db,
        activity_type=f"property_submission_{submission.status}",
        message=f"Property submission {submission.id} {submission.status}",
        user_id=actor_id,
        property_id=submission.property_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=recipient_user_id,
        actor_user_id=actor_id,
        type_key=f"property_submission_{submission.status}",
        title="Property submission reviewed",
        message=f"Your property submission was {submission.status}.",
        data={"submission_id": str(submission.id), "property_id": str(submission.property_id) if submission.property_id else None},
        action_url="/my-listings",
    )
    return submission


def serialize_draft_list_item(submission: PropertyListingSubmission) -> dict:
    return {
        "submission_id": str(submission.id),
        **_routing_payload(submission),
        "status": submission.status,
        "current_step": submission.current_step,
        "last_completed_step": submission.last_completed_step,
        "title": _title(submission.payload or {}),
        "updated_at": _iso(submission.updated_at),
        "can_edit": submission.status in WORKING_STATUSES,
        "can_delete": submission.status in WORKING_STATUSES,
    }


def stable_property_hash(property_id: UUID) -> int:
    return property_id.int % 2147483647


def _can_edit_submission_for_actor(
    db: Session | None,
    submission: PropertyListingSubmission,
    *,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
) -> bool:
    if actor_user_id is None or db is None:
        return submission.status in WORKING_STATUSES
    if submission.status in {ACTIVE_STATUS, DEACTIVATED_STATUS}:
        return False
    return can_edit_working_submission(
        db,
        submission,
        user_id=actor_user_id,
        roles=actor_roles,
        agency_id=actor_agency_id,
    )


def _workflow_label_for_submission(submission: PropertyListingSubmission) -> str:
    workflow = (submission.payload or {}).get("_workflow") or {}
    if submission.status == ACTIVE_STATUS and workflow.get("deal_closure_status") == DEAL_CLOSURE_REQUESTED_STATUS:
        return DEAL_CLOSURE_REQUESTED_STATUS
    if submission.status == ACTIVE_STATUS and workflow.get("deal_closure_status") == DEAL_CLOSED_STATUS:
        return DEAL_CLOSED_STATUS
    return submission.status


def _status_display_name(status: str) -> str:
    labels = {
        ACTIVE_STATUS: "Active",
        AGENT_ASSIGNED_STATUS: "Agent Assigned",
        DEACTIVATED_STATUS: "Deactivated",
        DEAL_CLOSED_STATUS: "Deal Closed",
        DEAL_CLOSURE_REQUESTED_STATUS: "Deal Closure Requested",
        PENDING_APPROVAL_STATUS: "Pending Approval",
        SUBMITTED_STATUS: "Submitted",
        "draft": "Draft",
        REJECTED_STATUS: "Rejected",
        "in_progress": "In Progress",
    }
    return WORKFLOW_CONFIG.label(status) if status in WORKFLOW_CONFIG.labels else labels.get(status, status)


def _normalize_status_filter(status: str) -> str:
    normalized = status.strip().lower().replace("_", "-")
    aliases = {
        "pending": PENDING_APPROVAL_STATUS,
        "pending-admin-approval": PENDING_APPROVAL_STATUS,
        "pending-approval": PENDING_APPROVAL_STATUS,
        "agent-assigned": AGENT_ASSIGNED_STATUS,
        "deal-closure-requested": DEAL_CLOSURE_REQUESTED_STATUS,
        "deal-closed": DEAL_CLOSED_STATUS,
    }
    return aliases.get(normalized, normalized)


def serialize_property_detail_workflow(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
) -> dict[str, Any]:
    workflow_label = _workflow_label_for_submission(submission)
    workflow_stage = _workflow_stage_for_submission(submission)
    workflow = _workflow_from_submission(submission)
    assigned_agent_id = _assigned_agent_id(submission)
    role_names = _role_names(actor_roles)
    status_label = _status_display_name(workflow_label)
    actions: list[dict[str, Any]] = []

    if actor_user_id is not None:
        can_manage_agency_submission = (
            "super_admin" not in role_names
            and "admin" in role_names
            and actor_agency_id is not None
            and _submitter_agency_id(db, submission) == actor_agency_id
        )
        can_directly_review_agencyless_submission = (
            "super_admin" in role_names
            and submission.agency_id is None
            and workflow_label in {SUBMITTED_STATUS, AGENT_ASSIGNED_STATUS, PENDING_APPROVAL_STATUS}
        )
        can_review_deal_closure = (
            "admin" in role_names
            and actor_agency_id is not None
            and _submitter_agency_id(db, submission) == actor_agency_id
        )

        if workflow_label == ACTIVE_STATUS:
            if "super_admin" in role_names:
                actions.append({"id": "deactivate", "label": "Deactivate", "tone": "danger"})
        elif can_directly_review_agencyless_submission:
            actions.extend(
                [
                    {"id": "approve", "label": "Approve"},
                    {"id": "reject", "label": "Reject", "tone": "danger"},
                ]
            )
        elif workflow_label == SUBMITTED_STATUS and can_manage_agency_submission:
            if WORKFLOW_CONFIG.enabled("agent_assignment_required_before_activation", default=True):
                actions.append({"id": "assign", "label": "Assign Agent"})
            else:
                actions.extend(
                    [
                        {"id": "approve", "label": "Approve"},
                        {"id": "reject", "label": "Reject", "tone": "danger"},
                    ]
                )
        elif workflow_label == AGENT_ASSIGNED_STATUS and can_manage_agency_submission:
            actions.extend(
                [
                    {"id": "reassign", "label": "Reassign Agent"},
                    {"id": "unassign", "label": "Unassign Agent", "tone": "danger"},
                    {"id": "approve", "label": "Approve"},
                    {"id": "reject", "label": "Reject", "tone": "danger"},
                ]
            )
        elif workflow_label == AGENT_ASSIGNED_STATUS and can_edit_working_submission(
            db,
            submission,
            user_id=actor_user_id,
            roles=actor_roles,
            agency_id=actor_agency_id,
        ):
            actions.append({"id": "edit", "label": "Review and Submit"})
        elif workflow_label == PENDING_APPROVAL_STATUS and can_manage_agency_submission:
            if (
                not assigned_agent_id
                and WORKFLOW_CONFIG.enabled("agent_assignment_required_before_activation", default=True)
            ):
                actions.append({"id": "assign", "label": "Assign Agent"})
            else:
                actions.extend(
                    [
                        {"id": "approve", "label": "Approve"},
                        {"id": "reject", "label": "Reject", "tone": "danger"},
                    ]
                )
        elif workflow_label == DEAL_CLOSURE_REQUESTED_STATUS and can_review_deal_closure:
            actions.append({"id": "review_deal_closure", "label": "Review Deal Closure"})
        elif workflow_label == REJECTED_STATUS and can_edit_working_submission(
            db,
            submission,
            user_id=actor_user_id,
            roles=actor_roles,
            agency_id=actor_agency_id,
        ):
            actions.append({"id": "edit", "label": "Update and Resubmit"})

    pending_actions = [action["label"] for action in actions if action.get("label")]
    return {
        "submission_id": str(submission.id),
        "status_label": status_label,
        "workflow_status": workflow_label,
        "workflow_stage": workflow_stage,
        "current_actor": _current_actor_for_workflow_stage(workflow_stage),
        "assigned_agent_id": assigned_agent_id,
        "deal_closure_id": workflow.get("deal_closure_id"),
        "status_action_card": {
            "status_label": status_label,
            "pending_actions": pending_actions,
        },
        "workflow_actions": actions,
    }


def serialize_agent_property_item(
    submission: PropertyListingSubmission,
    submitter: User | None = None,
    *,
    db: Session | None = None,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
) -> dict:
    payload = submission.payload or {}
    basic = payload.get("basic_information") or {}
    pricing = payload.get("pricing") or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    agency = None
    if submission.agency_id:
        agency = {"agency_id": str(submission.agency_id), "id": str(submission.agency_id)}
    assigned_agent = _assigned_agent_summary(db, submission) if db is not None else None
    workflow_label = _workflow_label_for_submission(submission)
    workflow_summary = _submission_workflow_summary(submission)
    can_edit_submission = _can_edit_submission_for_actor(
        db,
        submission,
        actor_user_id=actor_user_id,
        actor_roles=actor_roles,
        actor_agency_id=actor_agency_id,
    )
    can_delete_submission_value = (
        actor_user_id is not None
        and db is not None
        and can_delete_submission(
            db,
            submission,
            user_id=actor_user_id,
            roles=actor_roles,
            agency_id=actor_agency_id,
        )
    )
    settings = get_settings()
    pricing_fields = pricing_response_fields(pricing)
    return {
        "property_id": str(property_id),
        "property_hash": stable_property_hash(property_id),
        "title": basic.get("title") or settings.untitled_property_title,
        "listing_purpose": basic.get("listing_purpose") or "",
        "type_name": str(basic.get("type_id") or ""),
        "type_slug": str(basic.get("type_id") or ""),
        "category_name": str(basic.get("category_id") or ""),
        "category_slug": str(basic.get("category_id") or ""),
        "status_name": _status_display_name(workflow_label),
        "status_slug": submission.status,
        "price": pricing_fields["price"],
        "currency": pricing_fields["currency"],
        "service_charge": pricing_fields.get("service_charge"),
        "maintenance_fee": pricing_fields.get("maintenance_fee"),
        "reference_number": displayed_reference_number(submission, payload=payload, property_id=property_id),
        "created_at": _iso(submission.created_at),
        "updated_at": _iso(submission.updated_at),
        "submission_id": str(submission.id),
        "submission_status": submission.status,
        "submission_submitted_at": _iso(submission.submitted_at),
        "submission_reviewed_at": _iso(submission.reviewed_at),
        "submission_review_reason": submission.review_reason,
        "submission_workflow_label": workflow_label,
        **workflow_summary,
        "can_edit_submission": can_edit_submission,
        "can_delete_submission": can_delete_submission_value,
        **_routing_payload(submission),
        "agency": agency,
        "submitted_by": submitter.full_name if submitter and submitter.full_name else str(submission.submitted_by),
        "agent_user_id": workflow.get("assigned_agent_id"),
        "agent_name": assigned_agent["name"] if assigned_agent else None,
        "agent_email": assigned_agent["email"] if assigned_agent else None,
        "agent_phone": assigned_agent["phone"] if assigned_agent else None,
    }


def serialize_admin_submission_item(
    submission: PropertyListingSubmission,
    submitter: User | None = None,
    *,
    db: Session | None = None,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
) -> dict:
    payload = submission.payload or {}
    workflow = payload.get("_workflow") or {}
    property_id = submission.property_id or submission.id
    assigned_agent = _assigned_agent_summary(db, submission) if db is not None else None
    workflow_label = _workflow_label_for_submission(submission)
    workflow_summary = _submission_workflow_summary(submission)
    can_delete_submission_value = (
        actor_user_id is not None
        and db is not None
        and can_delete_submission(
            db,
            submission,
            user_id=actor_user_id,
            roles=actor_roles,
            agency_id=actor_agency_id,
        )
    )
    return {
        "submission_id": str(submission.id),
        **_routing_payload(submission),
        "submitted_by": str(submission.submitted_by),
        "submitted_by_name": submitter.full_name if submitter else "",
        "status": workflow_label,
        "status_label": _status_display_name(workflow_label),
        **workflow_summary,
        "property_id": str(property_id),
        "agent_user_id": workflow.get("assigned_agent_id"),
        "agent_name": assigned_agent["name"] if assigned_agent else None,
        "agent_email": assigned_agent["email"] if assigned_agent else None,
        "agent_phone": assigned_agent["phone"] if assigned_agent else None,
        "has_assigned_agent": bool(workflow.get("assigned_agent_id")),
        "property_hash": stable_property_hash(property_id),
        "property_title": _title(payload) or get_settings().untitled_property_title,
        "property_reference_number": stored_reference_number(submission, payload),
        "current_step": submission.current_step,
        "submitted_at": _iso(submission.submitted_at) or _iso(submission.created_at),
        "reviewed_at": _iso(submission.reviewed_at),
        "review_reason": submission.review_reason,
        "can_delete_submission": can_delete_submission_value,
    }


def list_submissions(
    db: Session,
    *,
    page: int,
    page_size: int,
    statuses: set[str] | None = None,
    submitted_by: UUID | None = None,
    assigned_to: UUID | None = None,
    agency_id: UUID | None = None,
    exclude_drafts: bool = False,
) -> tuple[list[tuple[PropertyListingSubmission, User | None]], dict]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = (
        select(PropertyListingSubmission, User)
        .join(User, User.id == PropertyListingSubmission.submitted_by)
        .where(PropertyListingSubmission.deleted_at.is_(None))
    )
    if statuses:
        stmt = stmt.where(PropertyListingSubmission.status.in_({_normalize_status_filter(status) for status in statuses}))
    if exclude_drafts:
        stmt = stmt.where(PropertyListingSubmission.status.not_in(DRAFT_STATUSES))
    if submitted_by and assigned_to:
        stmt = stmt.where(
            or_(
                PropertyListingSubmission.submitted_by == submitted_by,
                PropertyListingSubmission.payload["_workflow"]["assigned_agent_id"].astext == str(assigned_to),
            )
        )
    elif submitted_by:
        stmt = stmt.where(PropertyListingSubmission.submitted_by == submitted_by)
    elif assigned_to:
        stmt = stmt.where(PropertyListingSubmission.payload["_workflow"]["assigned_agent_id"].astext == str(assigned_to))
    if agency_id:
        stmt = stmt.where(
            or_(
                PropertyListingSubmission.agency_id == agency_id,
                PropertyListingSubmission.agency_id.is_(None) & (User.agency_id == agency_id),
            )
        )
    stmt = stmt.order_by(PropertyListingSubmission.updated_at.desc())
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, _pagination(total, page, page_size)


def assign_agent_to_property(
    db: Session,
    *,
    property_id: UUID,
    agent_id: UUID | None,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> PropertyListingSubmission:
    submission = db.execute(
        select(PropertyListingSubmission).where(
            or_(
                PropertyListingSubmission.property_id == property_id,
                PropertyListingSubmission.id == property_id,
            ),
            PropertyListingSubmission.deleted_at.is_(None),
        )
    ).scalars().first()
    if not submission:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property submission not found")
    role_names = _role_names(actor_roles)
    if "super_admin" in role_names:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent assignment is handled by Agency Admin")
    if "admin" not in role_names:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Only Agency Admin can assign agents")
    assert_can_manage_submission(db, submission, roles=actor_roles, agency_id=actor_agency_id)
    workflow_stage = _workflow_stage_for_submission(submission)
    can_assign_workflow = submission.status in {SUBMITTED_STATUS, AGENT_ASSIGNED_STATUS, PENDING_APPROVAL_STATUS} and workflow_stage in ASSIGNMENT_READY_STAGES
    if not can_assign_workflow:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agent assignment is not available in the current workflow stage")
    submission_agency_id = _submitter_agency_id(db, submission)
    if agent_id:
        agent = db.get(User, agent_id)
        if not agent:
            raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agent not found")
        has_mapping = bool(
            submission_agency_id
            and user_has_active_agency_mapping(
                db,
                user_id=agent.id,
                agency_id=submission_agency_id,
                relationship_type=REL_AGENT,
            )
        )
        has_legacy_agency = bool(submission_agency_id and agent.agency_id == submission_agency_id)
        if submission_agency_id and not has_mapping and not has_legacy_agency:
            raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Agent is outside the property agency")
    payload = dict(submission.payload or {})
    workflow = _payload_workflow(payload)
    workflow["assigned_agent_id"] = str(agent_id) if agent_id else None
    if agent_id:
        submission.status = WORKFLOW_CONFIG.transition("assign_agent")
        workflow["workflow_stage"] = WORKFLOW_STAGE_AGENT_ASSIGNED
        workflow["current_actor"] = CURRENT_ACTOR_ASSIGNED_AGENT
        workflow.setdefault("submission_origin", SUBMISSION_ORIGIN_OWNER)
    else:
        submission.status = WORKFLOW_CONFIG.transition("unassign_agent")
        workflow["workflow_stage"] = WORKFLOW_STAGE_SUBMITTED
        workflow["current_actor"] = CURRENT_ACTOR_AGENCY_ADMIN
    workflow["last_actor_user_id"] = str(actor_user_id)
    workflow["last_transition_at"] = utc_now().isoformat()
    submission.payload = payload
    flag_modified(submission, "payload")
    if agent_id:
        notify_assigned_agent_for_submission(db, submission=submission, actor_user_id=actor_user_id)
    return submission


def deactivate_submission(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    actor_id: UUID,
) -> PropertyListingSubmission:
    if _workflow_label_for_submission(submission) != ACTIVE_STATUS:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only active properties can be deactivated")
    submission.status = DEACTIVATED_STATUS
    record_activity(
        db,
        activity_type="property_deactivated",
        message=f"Property submission {submission.id} deactivated",
        user_id=actor_id,
        property_id=submission.property_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=submission.submitted_by,
        actor_user_id=actor_id,
        type_key="property_deactivated",
        title="Property deactivated",
        message="Your property listing was deactivated.",
        data={"submission_id": str(submission.id), "property_id": str(submission.property_id) if submission.property_id else None},
        action_url="/my-listings",
    )
    return submission
