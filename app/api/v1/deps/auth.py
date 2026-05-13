"""Dependency providers for authentication routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.repositories.profile_change_repository import ProfileChangeRepository
from app.repositories.user_remember_me_session_repository import UserRememberMeSessionRepository
from app.api.v1.deps.media_urls import get_media_url_signer
from app.services.auth_service import AuthService
from app.services.media_url_signer import MediaUrlSigner
from app.services.profile_update_service import ProfileUpdateService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_auth_repository(db: DBSessionDep) -> AuthRepository:
    """Provide an AuthRepository bound to the request database session.

    Args:
        db: Injected database session (from get_db).

    Returns:
        AuthRepository instance for auth routes.
    """
    return AuthRepository(db)


def get_auth_service(
    repo: AuthRepository = Depends(get_auth_repository),
    media_url_signer: MediaUrlSigner = Depends(get_media_url_signer),
) -> AuthService:
    """Provide an AuthService for signup, login, and profile endpoints.

    Args:
        repo: Injected AuthRepository (from get_auth_repository).
        media_url_signer: Signs S3-backed URLs in user responses (private bucket).

    Returns:
        AuthService instance.
    """
    return AuthService(
        repo,
        media_url_signer=media_url_signer,
        remember_me_repository=UserRememberMeSessionRepository(repo._db),
    )


def get_profile_update_service(db: DBSessionDep) -> ProfileUpdateService:
    """Provide ProfileUpdateService with repositories sharing one DB session."""
    return ProfileUpdateService(AuthRepository(db), ProfileChangeRepository(db))

