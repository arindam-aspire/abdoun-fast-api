"""Dependencies for location-aware property search."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.media_urls import get_media_url_signer
from app.db.session import get_db
from app.services.location_autocomplete_service import LocationAutocompleteService
from app.services.media_url_signer import MediaUrlSigner
from app.services.property_location_search_service import PropertyLocationSearchService

DBSessionDep = Annotated[Session, Depends(get_db)]


def get_location_autocomplete_service(db: DBSessionDep) -> LocationAutocompleteService:
    return LocationAutocompleteService(db)


def get_property_location_search_service(
    db: DBSessionDep,
    media_url_signer: MediaUrlSigner = Depends(get_media_url_signer),
) -> PropertyLocationSearchService:
    return PropertyLocationSearchService(db, media_url_signer=media_url_signer)
