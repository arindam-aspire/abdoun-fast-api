from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.live_schema import AgencyMaster, Role, User, UserAgencyMapping, UserRole


REL_AGENCY_ADMIN = "agency_admin"
REL_AGENCY_OWNER = "agency_owner"
REL_AGENT = "agent"
REL_PROPERTY_OWNER = "property_owner"
ACTIVE = "active"


def role_relationship_types(roles: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    names = {role.lower() for role in roles}
    relationships: list[str] = []
    if "admin" in names:
        relationships.append(REL_AGENCY_ADMIN)
    if "agent" in names:
        relationships.append(REL_AGENT)
    if "owner" in names or "registered_user" in names:
        relationships.append(REL_PROPERTY_OWNER)
    return tuple(relationships)


def active_mapping_query(*, user_id: UUID | None = None, agency_id: UUID | None = None, relationship_type: str | None = None):
    stmt = select(UserAgencyMapping).where(
        UserAgencyMapping.status == ACTIVE,
        UserAgencyMapping.deleted_at.is_(None),
    )
    if user_id is not None:
        stmt = stmt.where(UserAgencyMapping.user_id == user_id)
    if agency_id is not None:
        stmt = stmt.where(UserAgencyMapping.agency_id == agency_id)
    if relationship_type is not None:
        stmt = stmt.where(UserAgencyMapping.relationship_type == relationship_type)
    return stmt.order_by(UserAgencyMapping.is_primary.desc(), UserAgencyMapping.created_at.asc())


def active_mappings(
    db: Session,
    *,
    user_id: UUID | None = None,
    agency_id: UUID | None = None,
    relationship_type: str | None = None,
) -> list[UserAgencyMapping]:
    return db.execute(
        active_mapping_query(user_id=user_id, agency_id=agency_id, relationship_type=relationship_type)
    ).scalars().all()


def active_agency_ids_for_user(
    db: Session,
    user_id: UUID,
    *,
    relationship_types: tuple[str, ...] | None = None,
) -> tuple[UUID, ...]:
    stmt = select(UserAgencyMapping.agency_id).where(
        UserAgencyMapping.user_id == user_id,
        UserAgencyMapping.status == ACTIVE,
        UserAgencyMapping.deleted_at.is_(None),
    )
    if relationship_types:
        stmt = stmt.where(UserAgencyMapping.relationship_type.in_(relationship_types))
    return tuple(db.execute(stmt).scalars().all())


def primary_agency_id_for_context(db: Session, user: User, roles: tuple[str, ...]) -> UUID | None:
    relationships = role_relationship_types(roles)
    for relationship in (REL_AGENCY_ADMIN, REL_AGENCY_OWNER, REL_AGENT, REL_PROPERTY_OWNER):
        if relationship not in relationships:
            continue
        mapping = db.execute(active_mapping_query(user_id=user.id, relationship_type=relationship).limit(1)).scalar_one_or_none()
        if mapping:
            return mapping.agency_id
    return user.agency_id


def user_has_active_agency_mapping(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID,
    relationship_type: str | None = None,
) -> bool:
    stmt = active_mapping_query(user_id=user_id, agency_id=agency_id, relationship_type=relationship_type).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def active_agencies(db: Session):
    return (
        db.query(AgencyMaster)
        .filter(AgencyMaster.is_active.is_(True))
        .order_by(AgencyMaster.agency_name.asc())
    )


def selectable_owner_agencies(db: Session, *, user_id: UUID) -> list[AgencyMaster]:
    settings = get_settings()
    owner_mappings = active_mappings(db, user_id=user_id, relationship_type=REL_PROPERTY_OWNER)
    if owner_mappings and not settings.allow_owner_multiple_agencies:
        agency_ids = [mapping.agency_id for mapping in owner_mappings]
        return active_agencies(db).filter(AgencyMaster.id.in_(agency_ids)).all()
    return active_agencies(db).all()


def ensure_user_agency_mapping(
    db: Session,
    *,
    user_id: UUID,
    agency_id: UUID,
    relationship_type: str,
    actor_user_id: UUID | None = None,
    is_primary: bool | None = None,
) -> UserAgencyMapping:
    mapping = db.execute(
        active_mapping_query(user_id=user_id, agency_id=agency_id, relationship_type=relationship_type).limit(1)
    ).scalar_one_or_none()
    if mapping:
        return mapping

    if is_primary is None:
        is_primary = not active_mappings(db, user_id=user_id, relationship_type=relationship_type)

    mapping = UserAgencyMapping(
        user_id=user_id,
        agency_id=agency_id,
        relationship_type=relationship_type,
        status=ACTIVE,
        is_primary=is_primary,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(mapping)
    db.flush()
    return mapping


def agency_users_with_role(db: Session, *, agency_id: UUID, role_name: str) -> list[User]:
    relationship_type = REL_AGENCY_ADMIN if role_name == "admin" else role_name
    return db.execute(
        select(User)
        .join(UserAgencyMapping, UserAgencyMapping.user_id == User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserAgencyMapping.agency_id == agency_id,
            UserAgencyMapping.relationship_type == relationship_type,
            UserAgencyMapping.status == ACTIVE,
            UserAgencyMapping.deleted_at.is_(None),
            User.is_active.is_(True),
            Role.name == role_name,
        )
        .order_by(User.full_name.asc())
    ).scalars().all()


def agency_user_ids(db: Session, *, agency_id: UUID, relationship_types: tuple[str, ...] | None = None):
    stmt = select(UserAgencyMapping.user_id).where(
        UserAgencyMapping.agency_id == agency_id,
        UserAgencyMapping.status == ACTIVE,
        UserAgencyMapping.deleted_at.is_(None),
    )
    if relationship_types:
        stmt = stmt.where(UserAgencyMapping.relationship_type.in_(relationship_types))
    return stmt
