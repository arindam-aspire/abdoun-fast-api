"""Repository for agency registration and management."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.agency import Agency
from app.models.user import Role, User


class AgencyRepository:
    """Persistence operations for agency accounts and their admin users."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

    def agency_exists_by_email_or_phone(self, *, email: str, phone: str) -> bool:
        stmt: Select = select(Agency.id).where(or_(Agency.email == email, Agency.phone == phone))
        return self._db.execute(stmt).first() is not None

    def agency_phone_exists_excluding(self, *, phone: str, exclude_agency_id: uuid.UUID) -> bool:
        stmt: Select = select(Agency.id).where(Agency.phone == phone, Agency.id != exclude_agency_id)
        return self._db.execute(stmt).first() is not None

    def user_exists_by_email(self, email: str) -> bool:
        stmt: Select = select(User.id).where(User.email == email, User.deleted_at.is_(None))
        return self._db.execute(stmt).first() is not None

    def get_by_id(self, agency_id: uuid.UUID) -> Optional[Agency]:
        stmt: Select = select(Agency).where(Agency.id == agency_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> Optional[Agency]:
        stmt: Select = select(Agency).where(Agency.email == email)
        return self._db.execute(stmt).scalar_one_or_none()

    def list_agencies(self, *, skip: int, limit: int) -> list[Agency]:
        stmt: Select = select(Agency).order_by(Agency.created_at.desc()).offset(skip).limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def create_agency(self, **values) -> Agency:
        agency = Agency(**values)
        self._db.add(agency)
        self._db.flush()
        return agency

    def create_user(self, **values) -> User:
        user = User(**values)
        self._db.add(user)
        self._db.flush()
        return user

    def get_role_by_name(self, name: str) -> Optional[Role]:
        stmt: Select = select(Role).where(Role.name == name)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_id_with_roles(self, user_id: uuid.UUID) -> Optional[User]:
        stmt: Select = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id, User.deleted_at.is_(None))
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def delete_agency(self, agency: Agency) -> None:
        self._db.delete(agency)

    def add_roles_if_missing(self, roles: Iterable[tuple[str, str]]) -> None:
        for name, description in roles:
            if self.get_role_by_name(name) is None:
                self._db.add(Role(name=name, description=description))
