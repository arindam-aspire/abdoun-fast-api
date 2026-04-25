"""Dependency providers for profile picture presigned upload."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.services.profile_picture_upload_service import ProfilePictureUploadService
from app.services.s3_service import S3Service

from app.api.v1.deps.uploads import get_s3_service


def get_auth_repository_for_upload(db: Session = Depends(get_db)) -> AuthRepository:
    """AuthRepository bound to the request session (same session as get_current_user)."""
    return AuthRepository(db)


def get_profile_picture_upload_service(
    repo: AuthRepository = Depends(get_auth_repository_for_upload),
    s3_service: S3Service = Depends(get_s3_service),
) -> ProfilePictureUploadService:
    """ProfilePictureUploadService using shared S3 client configuration."""
    return ProfilePictureUploadService(repository=repo, s3_service=s3_service, settings=get_settings())
