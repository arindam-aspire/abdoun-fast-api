from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import AuthService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_auth_repository(db: DBSessionDep) -> AuthRepository:
    """FastAPI dependency that provides an AuthRepository instance."""
    return AuthRepository(db)


def get_auth_service(repo: AuthRepository = Depends(get_auth_repository)) -> AuthService:
    """FastAPI dependency that provides an AuthService instance."""
    return AuthService(repo)

