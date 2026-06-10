"""Repository for users, roles, permissions, and role assignment; list/get/update/delete."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Select, func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import Permission, Role, User, user_roles


class UserRepository:
    """Repository for user, role and permission persistence operations."""

    def __init__(self, db: Session) -> None:
        """Store the database session for all operations.

        Args:
            db: SQLAlchemy Session (request-scoped).
        """
        self._db = db

    # Users

    def _base_user_query(self) -> Select:
        """Base user query with roles eagerly loaded."""
        return select(User).options(selectinload(User.roles))

    def count_users(
        self,
        *,
        role_name: Optional[str] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> int:
        """Count distinct users matching optional role, search, and ``is_active`` filters."""
        inner = select(User.id).where(User.deleted_at.is_(None))
        if is_active is not None:
            inner = inner.where(User.is_active == is_active)
        if created_after is not None:
            inner = inner.where(User.created_at >= created_after)
        if created_before is not None:
            inner = inner.where(User.created_at <= created_before)
        if role_name:
            inner = inner.join(User.roles).where(Role.name == role_name)
        if search and search.strip():
            q = f"%{search.strip()}%"
            inner = inner.where(
                or_(
                    User.email.ilike(q),
                    User.full_name.ilike(q),
                    User.phone_number.ilike(q),
                )
            )
        inner = inner.distinct()
        stmt = select(func.count()).select_from(inner.subquery())
        return int(self._db.scalar(stmt) or 0)

    def list_users(
        self,
        *,
        limit: int,
        offset: int,
        role_name: Optional[str] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> List[User]:
        """List users with optional role, search, and ``is_active`` filters; paginated."""
        stmt = self._base_user_query().where(User.deleted_at.is_(None))

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        if created_after is not None:
            stmt = stmt.where(User.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(User.created_at <= created_before)

        if role_name:
            stmt = stmt.join(User.roles).where(Role.name == role_name)

        if search and search.strip():
            q = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.email.ilike(q),
                    User.full_name.ilike(q),
                    User.phone_number.ilike(q),
                )
            )

        stmt = stmt.order_by(User.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        result = self._db.execute(stmt).scalars().unique().all()
        return list(result)

    def get_user_with_roles_and_profile(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID with roles and profile loaded."""
        stmt = (
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .options(selectinload(User.roles), selectinload(User.profile))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Return user by id only if not soft-deleted (``deleted_at`` is NULL)."""
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_id_including_deleted(self, user_id: uuid.UUID) -> Optional[User]:
        """Return user by id including soft-deleted rows (for idempotent delete checks)."""
        stmt = select(User).where(User.id == user_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def soft_delete_user(self, user: User, *, deleted_by_id: uuid.UUID) -> None:
        """Soft-delete: set ``deleted_at`` / ``deleted_by`` and ``is_active`` to False (irreversible)."""
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        user.deleted_by = deleted_by_id

    def set_user_agency_id(self, *, user: User, agency_id: uuid.UUID) -> None:
        """Set ``users.agency_id`` for the given user (caller commits)."""
        user.agency_id = agency_id

    # Roles and permissions

    def list_roles_with_permissions(self) -> List[Role]:
        """List all roles with permissions eagerly loaded."""
        stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
        return list(self._db.execute(stmt).scalars().unique().all())

    def list_permissions(self) -> List[Permission]:
        """List all permissions ordered by code."""
        stmt = select(Permission).order_by(Permission.code)
        return list(self._db.execute(stmt).scalars().all())

    def get_role_by_id(self, role_id: uuid.UUID) -> Optional[Role]:
        """Get role by ID."""
        stmt = select(Role).where(Role.id == role_id)
        return self._db.execute(stmt).scalar_one_or_none()

    # Role assignment

    def assign_role_to_user(
        self,
        *,
        user: User,
        role: Role,
        assigned_by: uuid.UUID,
    ) -> None:
        """Insert user_roles row (user, role, assigned_by)."""
        self._db.execute(
            insert(user_roles).values(
                user_id=user.id,
                role_id=role.id,
                assigned_by=assigned_by,
            )
        )

    def remove_role_from_user(self, *, user: User, role: Role) -> None:
        """Remove role from user's roles (many-to-many)."""
        if role in user.roles:
            user.roles.remove(role)

    # Transactions

    def commit(self) -> None:
        """Commit the current transaction."""
        self._db.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        """Refresh instance from the DB."""
        self._db.refresh(instance)

