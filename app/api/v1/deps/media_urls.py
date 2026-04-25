"""Dependency: presigned GET signing for private S3 URLs in API responses."""

from fastapi import Depends

from app.core.config import get_settings
from app.services.media_url_signer import MediaUrlSigner
from app.services.s3_service import S3Service

from app.api.v1.deps.uploads import get_s3_service


def get_media_url_signer(s3: S3Service = Depends(get_s3_service)) -> MediaUrlSigner:
    """MediaUrlSigner using the same S3 client configuration as uploads."""
    return MediaUrlSigner(s3_service=s3, settings=get_settings())
