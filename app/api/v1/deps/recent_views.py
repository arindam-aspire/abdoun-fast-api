"""Dependency providers for recently viewed properties endpoints."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.media_urls import get_media_url_signer
from app.db.session import get_db
from app.repositories.recent_view_repository import RecentViewRepository
from app.services.media_url_signer import MediaUrlSigner
from app.services.recent_view_service import RecentViewService


def get_recent_view_repository(db: Session = Depends(get_db)) -> RecentViewRepository:
    """Provide request-scoped repository for recent views."""
    return RecentViewRepository(db)


def get_recent_view_service(
    repo: RecentViewRepository = Depends(get_recent_view_repository),
    media_url_signer: MediaUrlSigner = Depends(get_media_url_signer),
) -> RecentViewService:
    """Provide request-scoped service for recent views."""
    return RecentViewService(repo, media_url_signer=media_url_signer)
