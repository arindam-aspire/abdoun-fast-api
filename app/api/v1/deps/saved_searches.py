"""Dependency providers for saved-search routes."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.media_urls import get_media_url_signer
from app.db.session import get_db
from app.repositories.saved_search_repository import SavedSearchRepository
from app.services.media_url_signer import MediaUrlSigner
from app.services.saved_search_service import SavedSearchService


def get_saved_search_repository(db: Session = Depends(get_db)) -> SavedSearchRepository:
    """Provide SavedSearchRepository bound to current request DB session."""
    return SavedSearchRepository(db)


def get_saved_search_service(
    repo: SavedSearchRepository = Depends(get_saved_search_repository),
    media_url_signer: MediaUrlSigner = Depends(get_media_url_signer),
) -> SavedSearchService:
    """Provide SavedSearchService for user saved-search endpoints."""
    return SavedSearchService(repo, media_url_signer=media_url_signer)

