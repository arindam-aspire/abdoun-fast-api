from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """FastAPI dependency that provides a UserRepository instance."""
    return UserRepository(db)


def get_user_service(repo: UserRepository = Depends(get_user_repository)) -> UserService:
    """FastAPI dependency that provides a UserService instance."""
    return UserService(repo)

