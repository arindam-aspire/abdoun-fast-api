from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.models.live_schema import (
    AgencyMaster,
    Lead,
    PropertyListingSubmission,
    Role,
    User,
    UserAgencyMapping,
    UserRole,
)
from app.services.audit import record_activity
from app.services.leads import serialize_lead
from app.services.notifications import EmailPurpose, create_in_app_notification, send_email_notification
from app.services.property_submissions import serialize_submission
from app.services.public_properties import pagination_meta
from app.services.user_agencies import (
    REL_PROPERTY_OWNER,
    active_mappings,
    agency_user_ids,
    ensure_user_agency_mapping,
    user_has_active_agency_mapping,
)
from app.utils.api_response import raise_api_error
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_CONFLICT, STATUS_FORBIDDEN, STATUS_NOT_FOUND

OWNER_ROLES = ("owner", "registered_user")
ACTIVE_PROPERTY_STATUS = "active"
DEACTIVATED_PROPERTY_STATUS = "deactivated"
OWNER_DEACTIVATION_KEY = "_owner_deactivation"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _status_for_user(user: User) -> str:
    """Legacy status label used by agency owner list endpoints."""
    return "ACTIVE" if user.is_active else "SUSPENDED"


def _management_status_for_user(user: User) -> str:
    return "ACTIVE" if user.is_active else "INACTIVE"


def _property_count_for_owner(db: Session, *, user_id: UUID, agency_id: UUID) -> int:
    return db.execute(
        select(func.count(func.distinct(PropertyListingSubmission.property_id))).where(
            PropertyListingSubmission.submitted_by == user_id,
            PropertyListingSubmission.deleted_at.is_(None),
            PropertyListingSubmission.property_id.is_not(None),
            or_(
                PropertyListingSubmission.agency_id == agency_id,
                PropertyListingSubmission.agency_id.is_(None),
            ),
        )
    ).scalar() or 0


def _property_count_for_owner_all_agencies(db: Session, *, user_id: UUID) -> int:
    return db.execute(
        select(func.count(func.distinct(PropertyListingSubmission.property_id))).where(
            PropertyListingSubmission.submitted_by == user_id,
            PropertyListingSubmission.deleted_at.is_(None),
            PropertyListingSubmission.property_id.is_not(None),
        )
    ).scalar() or 0


def _lead_count_for_owner(db: Session, *, user_id: UUID, agency_id: UUID | None = None) -> int:
    property_ids = select(PropertyListingSubmission.property_id).where(
        PropertyListingSubmission.submitted_by == user_id,
        PropertyListingSubmission.deleted_at.is_(None),
        PropertyListingSubmission.property_id.is_not(None),
    )
    if agency_id is not None:
        property_ids = property_ids.where(
            or_(
                PropertyListingSubmission.agency_id == agency_id,
                PropertyListingSubmission.agency_id.is_(None),
            )
        )
    return db.execute(
        select(func.count()).select_from(Lead).where(Lead.property_id.in_(property_ids))
    ).scalar() or 0


def _owner_agencies(db: Session, *, user_id: UUID) -> list[dict[str, Any]]:
    mappings = active_mappings(db, user_id=user_id, relationship_type=REL_PROPERTY_OWNER)
    agencies_by_id = {
        agency.id: agency
        for agency in db.execute(
            select(AgencyMaster).where(AgencyMaster.id.in_([mapping.agency_id for mapping in mappings]))
        ).scalars().all()
    } if mappings else {}
    return [
        {
            "id": str(mapping.agency_id),
            "agency_name": agencies_by_id.get(mapping.agency_id).agency_name if agencies_by_id.get(mapping.agency_id) else "",
            "is_primary": mapping.is_primary,
            "created_at": _iso(mapping.created_at),
        }
        for mapping in mappings
    ]


def _assert_owner_user(db: Session, *, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Owner not found")
    has_owner_role = db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, Role.name.in_(list(OWNER_ROLES)))
        .limit(1)
    ).scalar_one_or_none()
    if not has_owner_role:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Selected user is not a property owner")
    return user


def _is_super_admin(roles: tuple[str, ...]) -> bool:
    return "super_admin" in {role.lower() for role in roles}


def _owner_in_agency(db: Session, *, user: User, agency_id: UUID) -> bool:
    if user_has_active_agency_mapping(
        db,
        user_id=user.id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
    ) or user.agency_id == agency_id:
        return True
    return bool(
        db.execute(
            select(PropertyListingSubmission.id)
            .where(
                PropertyListingSubmission.submitted_by == user.id,
                PropertyListingSubmission.agency_id == agency_id,
                PropertyListingSubmission.deleted_at.is_(None),
            )
            .limit(1)
        ).scalar_one_or_none()
    )


def _assert_can_manage_owner(
    db: Session,
    *,
    user: User,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> None:
    if _is_super_admin(actor_roles):
        return
    if actor_agency_id is None or not _owner_in_agency(db, user=user, agency_id=actor_agency_id):
        raise_api_error(
            status_code=STATUS_FORBIDDEN,
            code="FORBIDDEN",
            message="Insufficient permissions",
        )


def _assert_can_deactivate_owner(actor_roles: tuple[str, ...]) -> None:
    if not _is_super_admin(actor_roles):
        raise_api_error(
            status_code=STATUS_FORBIDDEN,
            code="FORBIDDEN",
            message="Insufficient permissions",
        )


def _owner_base_query() -> Any:
    return (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.deleted_at.is_(None),
            Role.name.in_(list(OWNER_ROLES)),
        )
        .distinct()
    )


def _apply_agency_scope(stmt: Any, db: Session, *, agency_id: UUID) -> Any:
    mapped_owner_ids = agency_user_ids(db, agency_id=agency_id, relationship_types=(REL_PROPERTY_OWNER,))
    submission_owner_ids = select(PropertyListingSubmission.submitted_by).where(
        PropertyListingSubmission.agency_id == agency_id,
        PropertyListingSubmission.deleted_at.is_(None),
    )
    return stmt.where(
        or_(
            User.id.in_(mapped_owner_ids),
            User.id.in_(submission_owner_ids),
            User.agency_id == agency_id,
        )
    )


def _apply_status_filter(stmt: Any, status: str | None) -> Any:
    normalized_status = (status or "").strip().lower()
    if not normalized_status or normalized_status == "all":
        return stmt
    if normalized_status in {"active", "enabled"}:
        return stmt.where(User.is_active.is_(True))
    if normalized_status in {"suspended", "inactive", "disabled"}:
        return stmt.where(User.is_active.is_(False))
    return stmt


def _apply_search_filter(stmt: Any, search: str | None) -> Any:
    if not search or not search.strip():
        return stmt
    pattern = f"%{search.strip()}%"
    return stmt.where(
        or_(
            User.full_name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone_number.ilike(pattern),
        )
    )


def serialize_owner(
    db: Session,
    user: User,
    *,
    agency_id: UUID | None = None,
    include_agencies: bool = True,
) -> dict[str, Any]:
    if agency_id is not None:
        property_count = _property_count_for_owner(db, user_id=user.id, agency_id=agency_id)
        lead_count = _lead_count_for_owner(db, user_id=user.id, agency_id=agency_id)
    else:
        property_count = _property_count_for_owner_all_agencies(db, user_id=user.id)
        lead_count = _lead_count_for_owner(db, user_id=user.id)
    status = _management_status_for_user(user)
    payload: dict[str, Any] = {
        "id": str(user.id),
        "owner_id": str(user.id),
        "ownerId": str(user.id),
        "full_name": user.full_name,
        "fullName": user.full_name,
        "email": user.email,
        "phone": user.phone_number or "",
        "phone_number": user.phone_number or "",
        "phoneNumber": user.phone_number or "",
        "status": status,
        "is_active": bool(user.is_active),
        "linked_properties_count": property_count,
        "linkedPropertiesCount": property_count,
        "linked_leads_count": lead_count,
        "linkedLeadsCount": lead_count,
        "property_owned": property_count,
        "nationality": None,
        "ssi": None,
        "address": None,
        "documents": [],
        "created_at": _iso(user.created_at),
        "createdAt": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
        "updatedAt": _iso(user.updated_at),
    }
    if include_agencies:
        agencies = _owner_agencies(db, user_id=user.id)
        payload["assigned_agencies"] = agencies
        payload["assignedAgencies"] = agencies
    return payload


def create_owner(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone_number: str | None,
    actor_agency_id: UUID | None,
) -> dict[str, Any]:
    """Create a selectable owner while enforcing the existing user identity rules."""
    normalized_email = email.strip().lower()
    if db.execute(select(User.id).where(func.lower(User.email) == normalized_email)).first():
        raise_api_error(
            status_code=STATUS_CONFLICT,
            code="DUPLICATE_OWNER",
            message="An owner account with this email already exists",
            details=[{"field": "email", "code": "duplicate", "message": "Email is already in use"}],
        )
    if phone_number and db.execute(select(User.id).where(User.phone_number == phone_number)).first():
        raise_api_error(
            status_code=STATUS_CONFLICT,
            code="DUPLICATE_OWNER",
            message="An owner account with this phone number already exists",
            details=[{"field": "phone_number", "code": "duplicate", "message": "Phone number is already in use"}],
        )

    # Local import avoids coupling authentication module initialization to owner routes.
    from app.services.auth import create_user

    user = create_user(
        db,
        full_name=full_name.strip(),
        email=normalized_email,
        phone_number=phone_number,
        password=None,
        role="owner",
        agency_id=actor_agency_id,
    )
    return serialize_owner(db, user, agency_id=actor_agency_id, include_agencies=True)


def list_agency_owners(
    db: Session,
    *,
    agency_id: UUID,
    page: int,
    page_size: int,
    search: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = _apply_agency_scope(_owner_base_query(), db, agency_id=agency_id).order_by(User.created_at.desc())
    stmt = _apply_search_filter(stmt, search)
    stmt = _apply_status_filter(stmt, status)

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    users = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    items = [
        {
            "owner_id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone_number or "",
            "nationality": None,
            "ssi": None,
            "address": None,
            "documents": [],
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
            "status": _status_for_user(user),
            "property_owned": _property_count_for_owner(db, user_id=user.id, agency_id=agency_id),
        }
        for user in users
    ]
    total_pages = math.ceil(total / page_size) if total else 1
    pagination = {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }
    return items, pagination


def list_platform_owners(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None = None,
    status: str | None = None,
    agency_id: UUID | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = _owner_base_query().order_by(User.created_at.desc())
    if agency_id is not None:
        stmt = _apply_agency_scope(stmt, db, agency_id=agency_id)
    stmt = _apply_search_filter(stmt, search)
    stmt = _apply_status_filter(stmt, status)

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    users = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    items = [
        {
            "owner_id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone_number or "",
            "nationality": None,
            "ssi": None,
            "address": None,
            "documents": [],
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
            "status": _status_for_user(user),
            "property_owned": _property_count_for_owner_all_agencies(db, user_id=user.id),
            "assigned_agencies": _owner_agencies(db, user_id=user.id),
        }
        for user in users
    ]
    total_pages = math.ceil(total / page_size) if total else 1
    pagination = {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }
    return items, pagination


def list_owners(
    db: Session,
    *,
    agency_id: UUID | None,
    roles: tuple[str, ...],
    page: int,
    page_size: int,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    search: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    is_super_admin = _is_super_admin(roles)
    if not is_super_admin and agency_id is None:
        empty_pagination = pagination_meta(0, page, page_size)
        return {"owners": [], "items": [], **empty_pagination, "pagination": empty_pagination}

    stmt = _owner_base_query()
    scoped_agency_id = None if is_super_admin else agency_id
    if not is_super_admin and agency_id is not None:
        stmt = _apply_agency_scope(stmt, db, agency_id=agency_id)
    stmt = _apply_search_filter(stmt, search)
    stmt = _apply_status_filter(stmt, status)

    sort_columns = {
        "created_at": User.created_at,
        "createdAt": User.created_at,
        "updated_at": User.updated_at,
        "updatedAt": User.updated_at,
        "email": User.email,
        "full_name": User.full_name,
        "fullName": User.full_name,
        "phone": User.phone_number,
        "phoneNumber": User.phone_number,
        "status": User.is_active,
    }
    sort_column = sort_columns.get(sort_by, User.created_at)
    stmt = stmt.order_by(sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc().nullslast())

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    users = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    items = [
        serialize_owner(
            db,
            user,
            agency_id=scoped_agency_id,
            include_agencies=is_super_admin,
        )
        for user in users
    ]
    pagination = pagination_meta(total, page, page_size)
    return {"owners": items, "items": items, **pagination, "pagination": pagination}


def get_owner(
    db: Session,
    *,
    owner_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> dict[str, Any]:
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)
    agency_scope = None if _is_super_admin(actor_roles) else actor_agency_id
    return serialize_owner(
        db,
        user,
        agency_id=agency_scope,
        include_agencies=_is_super_admin(actor_roles),
    )


def update_owner(
    db: Session,
    *,
    owner_id: UUID,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    full_name: str | None = None,
    email: str | None = None,
    phone_number: str | None = None,
) -> dict[str, Any]:
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)

    if full_name is not None:
        cleaned_name = full_name.strip()
        if not cleaned_name:
            raise_api_error(status_code=STATUS_BAD_REQUEST, code="VALIDATION_ERROR", message="full_name cannot be empty")
        user.full_name = cleaned_name

    if email is not None:
        cleaned_email = email.strip().lower()
        if not cleaned_email:
            raise_api_error(status_code=STATUS_BAD_REQUEST, code="VALIDATION_ERROR", message="email cannot be empty")
        existing = db.execute(
            select(User.id).where(User.email == cleaned_email, User.id != user.id, User.deleted_at.is_(None))
        ).scalar_one_or_none()
        if existing:
            raise_api_error(
                status_code=STATUS_CONFLICT,
                code="DUPLICATE_OWNER",
                message="Email is already in use",
                details=[{"field": "email", "code": "duplicate", "message": "Email is already in use"}],
            )
        user.email = cleaned_email

    if phone_number is not None:
        cleaned_phone = phone_number.strip()
        existing = (
            db.execute(
                select(User.id).where(
                    User.phone_number == cleaned_phone,
                    User.id != user.id,
                    User.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if cleaned_phone
            else None
        )
        if existing:
            raise_api_error(
                status_code=STATUS_CONFLICT,
                code="DUPLICATE_OWNER",
                message="Phone number is already in use",
                details=[
                    {
                        "field": "phone_number",
                        "code": "duplicate",
                        "message": "Phone number is already in use",
                    }
                ],
            )
        user.phone_number = cleaned_phone or None

    user.updated_at = _utc_now()
    record_activity(
        db,
        activity_type="owner_updated",
        message=f"Owner {owner_id} profile updated",
        user_id=actor_user_id,
    )
    agency_scope = None if _is_super_admin(actor_roles) else actor_agency_id
    return serialize_owner(
        db,
        user,
        agency_id=agency_scope,
        include_agencies=_is_super_admin(actor_roles),
    )


def _hide_owner_properties(db: Session, *, owner: User, actor_id: UUID) -> int:
    submissions = db.execute(
        select(PropertyListingSubmission).where(
            PropertyListingSubmission.submitted_by == owner.id,
            PropertyListingSubmission.deleted_at.is_(None),
            PropertyListingSubmission.status == ACTIVE_PROPERTY_STATUS,
        )
    ).scalars().all()
    now = _utc_now().isoformat()
    count = 0
    for submission in submissions:
        payload = dict(submission.payload or {})
        payload[OWNER_DEACTIVATION_KEY] = {
            "deactivated_by_owner_id": str(owner.id),
            "deactivated_by_actor_id": str(actor_id),
            "previous_status": submission.status,
            "deactivated_at": now,
        }
        submission.status = DEACTIVATED_PROPERTY_STATUS
        submission.payload = payload
        flag_modified(submission, "payload")
        count += 1
    return count


def _restore_owner_properties(db: Session, *, owner: User) -> int:
    submissions = db.execute(
        select(PropertyListingSubmission).where(
            PropertyListingSubmission.submitted_by == owner.id,
            PropertyListingSubmission.deleted_at.is_(None),
            PropertyListingSubmission.status == DEACTIVATED_PROPERTY_STATUS,
        )
    ).scalars().all()
    count = 0
    for submission in submissions:
        payload = dict(submission.payload or {})
        owner_deactivation = payload.get(OWNER_DEACTIVATION_KEY) or {}
        if owner_deactivation.get("deactivated_by_owner_id") != str(owner.id):
            continue
        previous_status = owner_deactivation.get("previous_status") or ACTIVE_PROPERTY_STATUS
        submission.status = previous_status
        payload.pop(OWNER_DEACTIVATION_KEY, None)
        submission.payload = payload
        flag_modified(submission, "payload")
        count += 1
    return count


def deactivate_owner(
    db: Session,
    *,
    owner_id: UUID,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    reason: str | None = None,
) -> dict[str, Any]:
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)
    _assert_can_deactivate_owner(actor_roles)
    if not user.is_active:
        raise_api_error(status_code=STATUS_BAD_REQUEST, code="VALIDATION_ERROR", message="Owner is already inactive")

    user.is_active = False
    user.updated_at = _utc_now()
    hidden_count = _hide_owner_properties(db, owner=user, actor_id=actor_user_id)

    message = f"Owner {owner_id} deactivated"
    if reason:
        message = f"{message}: {reason}"
    record_activity(
        db,
        activity_type="owner_deactivated",
        message=message,
        user_id=actor_user_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=user.id,
        actor_user_id=actor_user_id,
        type_key="owner_deactivated",
        title="Account deactivated",
        message="Your owner account has been deactivated. Your property listings are hidden from the website.",
        data={"owner_id": str(user.id), "hidden_properties": hidden_count, "reason": reason},
        action_url="/account",
    )
    if user.email:
        send_email_notification(
            to_email=user.email,
            subject="Your Abdoun owner account was deactivated",
            body=(
                "Your owner account has been deactivated. "
                "Your property listings are hidden from the website but retained in our system."
                + (f" Reason: {reason}" if reason else "")
            ),
            purpose=EmailPurpose.ACCOUNT_NOTIFICATION,
        )

    agency_scope = None if _is_super_admin(actor_roles) else actor_agency_id
    result = serialize_owner(
        db,
        user,
        agency_id=agency_scope,
        include_agencies=_is_super_admin(actor_roles),
    )
    result["hidden_properties_count"] = hidden_count
    return result


def activate_owner(
    db: Session,
    *,
    owner_id: UUID,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
) -> dict[str, Any]:
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)
    if user.is_active:
        raise_api_error(status_code=STATUS_BAD_REQUEST, code="VALIDATION_ERROR", message="Owner is already active")

    user.is_active = True
    user.updated_at = _utc_now()
    restored_count = _restore_owner_properties(db, owner=user)

    record_activity(
        db,
        activity_type="owner_activated",
        message=f"Owner {owner_id} activated",
        user_id=actor_user_id,
    )
    create_in_app_notification(
        db,
        recipient_user_id=user.id,
        actor_user_id=actor_user_id,
        type_key="owner_activated",
        title="Account reactivated",
        message="Your owner account has been reactivated. Your property listings have been restored.",
        data={"owner_id": str(user.id), "restored_properties": restored_count},
        action_url="/account",
    )
    if user.email:
        send_email_notification(
            to_email=user.email,
            subject="Your Abdoun owner account was reactivated",
            body="Your owner account has been reactivated and your linked property listings have been restored.",
            purpose=EmailPurpose.ACCOUNT_NOTIFICATION,
        )

    agency_scope = None if _is_super_admin(actor_roles) else actor_agency_id
    result = serialize_owner(
        db,
        user,
        agency_id=agency_scope,
        include_agencies=_is_super_admin(actor_roles),
    )
    result["restored_properties_count"] = restored_count
    return result


def update_owner_status(
    db: Session,
    *,
    owner_id: UUID,
    actor_user_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    status: str,
    reason: str | None = None,
    legacy_status_label: bool = False,
) -> dict[str, Any]:
    normalized = status.strip().upper()
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)
    agency_scope = None if _is_super_admin(actor_roles) else actor_agency_id

    if normalized in {"ACTIVE", "ENABLED"}:
        if user.is_active:
            result = serialize_owner(
                db,
                user,
                agency_id=agency_scope,
                include_agencies=_is_super_admin(actor_roles),
            )
            result["status"] = "ACTIVE"
            return result
        result = activate_owner(
            db,
            owner_id=owner_id,
            actor_user_id=actor_user_id,
            actor_roles=actor_roles,
            actor_agency_id=actor_agency_id,
        )
        result["status"] = "ACTIVE"
        return result

    if normalized in {"SUSPENDED", "INACTIVE", "DISABLED"}:
        _assert_can_deactivate_owner(actor_roles)
        if not user.is_active:
            result = serialize_owner(
                db,
                user,
                agency_id=agency_scope,
                include_agencies=_is_super_admin(actor_roles),
            )
            result["status"] = "SUSPENDED" if legacy_status_label else "INACTIVE"
            return result
        result = deactivate_owner(
            db,
            owner_id=owner_id,
            actor_user_id=actor_user_id,
            actor_roles=actor_roles,
            actor_agency_id=actor_agency_id,
            reason=reason,
        )
        result["status"] = "SUSPENDED" if legacy_status_label else "INACTIVE"
        return result

    raise_api_error(
        status_code=STATUS_BAD_REQUEST,
        code="VALIDATION_ERROR",
        message="Invalid owner status",
    )


def list_owner_properties(
    db: Session,
    *,
    owner_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)

    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    stmt = select(PropertyListingSubmission).where(
        PropertyListingSubmission.submitted_by == owner_id,
        PropertyListingSubmission.deleted_at.is_(None),
    )
    if not _is_super_admin(actor_roles) and actor_agency_id is not None:
        stmt = stmt.where(
            or_(
                PropertyListingSubmission.agency_id == actor_agency_id,
                PropertyListingSubmission.agency_id.is_(None),
            )
        )
    stmt = stmt.order_by(PropertyListingSubmission.updated_at.desc())

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    submissions = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    items = [serialize_submission(submission) for submission in submissions]
    pagination = pagination_meta(total, page, page_size)
    return {"items": items, "properties": items, **pagination, "pagination": pagination}


def list_owner_leads(
    db: Session,
    *,
    owner_id: UUID,
    actor_roles: tuple[str, ...],
    actor_agency_id: UUID | None,
    page: int,
    page_size: int,
    status: str | None = None,
) -> dict[str, Any]:
    user = _assert_owner_user(db, user_id=owner_id)
    _assert_can_manage_owner(db, user=user, actor_roles=actor_roles, actor_agency_id=actor_agency_id)

    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    property_ids = select(PropertyListingSubmission.property_id).where(
        PropertyListingSubmission.submitted_by == owner_id,
        PropertyListingSubmission.deleted_at.is_(None),
        PropertyListingSubmission.property_id.is_not(None),
    )
    if not _is_super_admin(actor_roles) and actor_agency_id is not None:
        property_ids = property_ids.where(
            or_(
                PropertyListingSubmission.agency_id == actor_agency_id,
                PropertyListingSubmission.agency_id.is_(None),
            )
        )

    stmt = select(Lead).where(Lead.property_id.in_(property_ids)).order_by(Lead.updated_at.desc())
    if status and status.strip():
        stmt = stmt.where(Lead.status == status.strip())

    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    leads = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    items = [serialize_lead(db, lead) for lead in leads]
    pagination = pagination_meta(total, page, page_size)
    return {"items": items, "leads": items, **pagination, "pagination": pagination}


def assign_owner_to_agency(
    db: Session,
    *,
    owner_id: UUID,
    agency_id: UUID,
    actor_user_id: UUID,
) -> UserAgencyMapping:
    _assert_owner_user(db, user_id=owner_id)
    agency = db.get(AgencyMaster, agency_id)
    if not agency or not agency.is_active or not agency.is_verified:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Active verified agency not found")

    settings = get_settings()
    active_owner_mappings = active_mappings(db, user_id=owner_id, relationship_type=REL_PROPERTY_OWNER)
    if not settings.allow_owner_multiple_agencies:
        for mapping in active_owner_mappings:
            if mapping.agency_id == agency_id:
                mapping.is_primary = True
                mapping.updated_by = actor_user_id
                record_activity(
                    db,
                    activity_type="owner_agency_mapping_confirmed",
                    message=f"Owner {owner_id} agency assignment confirmed for agency {agency_id}",
                    user_id=actor_user_id,
                )
                return mapping
            mapping.status = "inactive"
            mapping.deleted_at = _utc_now()
            mapping.updated_by = actor_user_id

    mapping = ensure_user_agency_mapping(
        db,
        user_id=owner_id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
        actor_user_id=actor_user_id,
        is_primary=True,
    )
    record_activity(
        db,
        activity_type="owner_agency_mapping_updated",
        message=f"Owner {owner_id} assigned to agency {agency_id}",
        user_id=actor_user_id,
    )
    return mapping
