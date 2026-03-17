from __future__ import annotations

from typing import Optional

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import AgentProfile, Role, User


class AuthRepository:
    """Repository for authentication-related user, role, and profile persistence."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # Generic helpers -----------------------------------------------------

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)

    # User lookups --------------------------------------------------------

    def user_exists_by_email_or_phone(self, *, email: str, phone: str) -> bool:
        stmt: Select = select(User).where(
            (User.email == email) | (User.phone_number == phone)
        )
        return self._db.execute(stmt).first() is not None

    def get_user_by_email(self, email: str) -> Optional[User]:
        stmt: Select = select(User).where(User.email == email)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_email_or_phone_with_profile(
        self,
        username: str,
    ) -> Optional[User]:
        stmt: Select = (
            select(User)
            .options(selectinload(User.profile))
            .where(
                (User.email == username) | (User.phone_number == username)
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_cognito_sub_with_profile(
        self,
        cognito_sub: str,
    ) -> Optional[User]:
        stmt: Select = (
            select(User)
            .options(selectinload(User.profile))
            .where(User.cognito_sub == cognito_sub)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_cognito_or_email(
        self,
        *,
        cognito_sub: str,
        email: str,
    ) -> Optional[User]:
        stmt: Select = select(User).where(
            (User.cognito_sub == cognito_sub) | (User.email == email)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def create_user(
        self,
        *,
        email: str,
        full_name: str,
        phone_number: str,
        cognito_sub: Optional[str],
        is_active: bool,
    ) -> User:
        user = User(
            email=email,
            full_name=full_name,
            phone_number=phone_number,
            is_active=is_active,
            cognito_sub=cognito_sub,
        )
        self._db.add(user)
        return user

    def ensure_agent_profile_loaded(self, user: User) -> None:
        if user.profile is not None:
            return
        # Fallback query for AgentProfile if lazy relationship is not configured
        stmt: Select = select(AgentProfile).where(AgentProfile.user_id == user.id)
        profile = self._db.execute(stmt).scalar_one_or_none()
        if profile:
            user.profile = profile

    # Roles ---------------------------------------------------------------

    def get_role_by_name(self, name: str) -> Optional[Role]:
        stmt: Select = select(Role).where(Role.name == name)
        return self._db.execute(stmt).scalar_one_or_none()

    # Permissions helpers (wrapper for existing permission utilities) -----

    def get_agent_profile_for_user(self, user_id) -> Optional[AgentProfile]:
        stmt: Select = select(AgentProfile).where(AgentProfile.user_id == user_id)
        return self._db.execute(stmt).scalar_one_or_none()

