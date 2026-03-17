from typing import List, Optional
import uuid

from sqlalchemy import Select, and_, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import Permission, Role, User, user_roles


class UserRepository:
    """Repository for user, role and permission persistence operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # Users

    def _base_user_query(self) -> Select:
        return select(User).options(selectinload(User.roles))

    def list_users(
        self,
        *,
        limit: int,
        offset: int,
        role_name: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[User]:
        stmt = self._base_user_query()

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

        stmt = stmt.offset(offset).limit(limit).distinct()
        result = self._db.execute(stmt).scalars().unique().all()
        return list(result)

    def get_user_with_roles_and_profile(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles), selectinload(User.profile))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def soft_delete_user(self, user: User) -> None:
        user.is_active = False

    # Roles and permissions

    def list_roles_with_permissions(self) -> List[Role]:
        stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
        return list(self._db.execute(stmt).scalars().unique().all())

    def list_permissions(self) -> List[Permission]:
        stmt = select(Permission).order_by(Permission.code)
        return list(self._db.execute(stmt).scalars().all())

    def get_role_by_id(self, role_id: uuid.UUID) -> Optional[Role]:
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
        self._db.execute(
            insert(user_roles).values(
                user_id=user.id,
                role_id=role.id,
                assigned_by=assigned_by,
            )
        )

    def remove_role_from_user(self, *, user: User, role: Role) -> None:
        if role in user.roles:
            user.roles.remove(role)

    # Transactions

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

