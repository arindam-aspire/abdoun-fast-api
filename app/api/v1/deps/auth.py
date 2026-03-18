"""Dependency providers for authentication routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import AuthService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_auth_repository(db: DBSessionDep) -> AuthRepository:
    """Provide an AuthRepository bound to the request database session.

    Args:
        db: Injected database session (from get_db).

    Returns:
        AuthRepository instance for auth routes.
    """
    return AuthRepository(db)


def get_auth_service(repo: AuthRepository = Depends(get_auth_repository)) -> AuthService:
    """Provide an AuthService for signup, login, and profile endpoints.

    Args:
        repo: Injected AuthRepository (from get_auth_repository).

    Returns:
        AuthService instance.
    """
    return AuthService(repo)

