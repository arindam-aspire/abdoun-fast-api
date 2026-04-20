"""Dependency providers for favorites routes."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.favorite_repository import FavoriteRepository
from app.services.favorite_service import FavoriteService


def get_favorite_repository(db: Session = Depends(get_db)) -> FavoriteRepository:
    """Provide FavoriteRepository bound to current request DB session."""
    return FavoriteRepository(db)


def get_favorite_service(
    repo: FavoriteRepository = Depends(get_favorite_repository),
) -> FavoriteService:
    """Provide FavoriteService for user favorites endpoints."""
    return FavoriteService(repo)

