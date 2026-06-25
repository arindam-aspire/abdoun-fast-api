from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.live_schema import PropertyListingSubmission, Role, User, UserRole
from app.services.user_agencies import REL_PROPERTY_OWNER, agency_user_ids


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


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
