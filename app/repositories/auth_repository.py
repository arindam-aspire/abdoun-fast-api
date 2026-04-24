"""Repository for auth: user lookup by email/phone/cognito_sub, create user, roles, profile."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import AgentProfile, Role, User


class AuthRepository:
    """Repository for authentication-related user, role, and profile persistence."""

    def __init__(self, db: Session) -> None:
        """Store the database session for all operations.

        Args:
            db: SQLAlchemy Session (request-scoped).
        """
        self._db = db

    # Generic helpers -----------------------------------------------------

    def commit(self) -> None:
        """Commit the current transaction."""
        self._db.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        """Refresh instance from the DB."""
        self._db.refresh(instance)

    # User lookups --------------------------------------------------------

    def user_exists_by_email_or_phone(self, *, email: str, phone: str) -> bool:
        """Return True if a user exists with the given email or phone."""
        stmt: Select = select(User).where(
            (User.email == email) | (User.phone_number == phone)
        )
        return self._db.execute(stmt).first() is not None

    def user_exists_by_email_excluding(self, *, email: str, exclude_user_id: uuid.UUID) -> bool:
        """Return True if another user (not exclude_user_id) already has this email."""
        stmt: Select = select(User.id).where(User.email == email, User.id != exclude_user_id)
        return self._db.execute(stmt).first() is not None

    def user_exists_by_phone_excluding(self, *, phone: str, exclude_user_id: uuid.UUID) -> bool:
        """Return True if another user already has this phone number."""
        stmt: Select = select(User.id).where(User.phone_number == phone, User.id != exclude_user_id)
        return self._db.execute(stmt).first() is not None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (no eager loads)."""
        stmt: Select = select(User).where(User.email == email)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_email_or_phone_with_profile(
        self,
        username: str,
    ) -> Optional[User]:
        """Get user by email or phone with profile loaded."""
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
        """Get user by Cognito sub with profile loaded."""
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
        """Get user by cognito_sub or email (no profile)."""
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
        """Create and persist a new user."""
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
        """Look up role by name."""
        stmt: Select = select(Role).where(Role.name == name)
        return self._db.execute(stmt).scalar_one_or_none()

    # Permissions helpers (wrapper for existing permission utilities) -----

    def get_agent_profile_for_user(self, user_id) -> Optional[AgentProfile]:
        """Get agent profile for the given user_id."""
        stmt: Select = select(AgentProfile).where(AgentProfile.user_id == user_id)
        return self._db.execute(stmt).scalar_one_or_none()

