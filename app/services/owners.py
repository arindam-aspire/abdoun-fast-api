from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.core.config import get_settings
from app.models.live_schema import AgencyMaster, PropertyListingSubmission, Role, User, UserAgencyMapping, UserRole
from app.services.audit import record_activity
from app.services.user_agencies import REL_PROPERTY_OWNER, active_mappings, agency_user_ids, ensure_user_agency_mapping
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_NOT_FOUND


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _status_for_user(user: User) -> str:
    return "ACTIVE" if user.is_active else "SUSPENDED"


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
        .where(UserRole.user_id == user.id, Role.name.in_(["owner", "registered_user"]))
        .limit(1)
    ).scalar_one_or_none()
    if not has_owner_role:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Selected user is not a property owner")
    return user


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
    mapped_owner_ids = agency_user_ids(db, agency_id=agency_id, relationship_types=(REL_PROPERTY_OWNER,))
    submission_owner_ids = select(PropertyListingSubmission.submitted_by).where(
        PropertyListingSubmission.agency_id == agency_id,
        PropertyListingSubmission.deleted_at.is_(None),
    )
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.deleted_at.is_(None),
            Role.name.in_(["owner", "registered_user"]),
            or_(
                User.id.in_(mapped_owner_ids),
                User.id.in_(submission_owner_ids),
                User.agency_id == agency_id,
            ),
        )
        .distinct()
        .order_by(User.created_at.desc())
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern), User.phone_number.ilike(pattern)))
    normalized_status = (status or "").strip().lower()
    if normalized_status and normalized_status != "all":
        if normalized_status in {"active", "enabled"}:
            stmt = stmt.where(User.is_active.is_(True))
        elif normalized_status in {"suspended", "inactive", "disabled"}:
            stmt = stmt.where(User.is_active.is_(False))

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
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.deleted_at.is_(None),
            Role.name.in_(["owner", "registered_user"]),
        )
        .distinct()
        .order_by(User.created_at.desc())
    )
    if agency_id is not None:
        mapped_owner_ids = agency_user_ids(db, agency_id=agency_id, relationship_types=(REL_PROPERTY_OWNER,))
        submission_owner_ids = select(PropertyListingSubmission.submitted_by).where(
            PropertyListingSubmission.agency_id == agency_id,
            PropertyListingSubmission.deleted_at.is_(None),
        )
        stmt = stmt.where(or_(User.id.in_(mapped_owner_ids), User.id.in_(submission_owner_ids)))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern), User.phone_number.ilike(pattern)))
    normalized_status = (status or "").strip().lower()
    if normalized_status and normalized_status != "all":
        if normalized_status in {"active", "enabled"}:
            stmt = stmt.where(User.is_active.is_(True))
        elif normalized_status in {"suspended", "inactive", "disabled"}:
            stmt = stmt.where(User.is_active.is_(False))

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
