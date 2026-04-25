"""Dependency providers for property routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.media_urls import get_media_url_signer
from app.db.session import get_db
from app.services.media_url_signer import MediaUrlSigner
from app.services.property_search_service import PropertySearchService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_property_search_service(
    db: DBSessionDep,
    media_url_signer: MediaUrlSigner = Depends(get_media_url_signer),
) -> PropertySearchService:
    """Provide a PropertySearchService for property list/detail/similar endpoints.

    Args:
        db: Injected database session (from get_db).
        media_url_signer: Presigned GET for S3 media in responses.

    Returns:
        PropertySearchService instance.
    """
    return PropertySearchService(db, media_url_signer=media_url_signer)

