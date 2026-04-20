"""Dependency providers for recently viewed properties endpoints."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.recent_view_repository import RecentViewRepository
from app.services.recent_view_service import RecentViewService


def get_recent_view_repository(db: Session = Depends(get_db)) -> RecentViewRepository:
    """Provide request-scoped repository for recent views."""
    return RecentViewRepository(db)


def get_recent_view_service(
    repo: RecentViewRepository = Depends(get_recent_view_repository),
) -> RecentViewService:
    """Provide request-scoped service for recent views."""
    return RecentViewService(repo)
