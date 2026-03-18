"""Dependency providers for user management routes."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """Provide a UserRepository bound to the request database session.

    Args:
        db: Injected database session (from get_db).

    Returns:
        UserRepository instance for user management routes.
    """
    return UserRepository(db)


def get_user_service(repo: UserRepository = Depends(get_user_repository)) -> UserService:
    """Provide a UserService for list/update/delete user and role assignment.

    Args:
        repo: Injected UserRepository (from get_user_repository).

    Returns:
        UserService instance.
    """
    return UserService(repo)

