"""Dependency providers for upload helper endpoints."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.services.s3_service import S3Service
from app.services.upload_service import UploadService


def get_upload_repository(db: Session = Depends(get_db)) -> PropertySubmissionRepository:
    """Provide PropertySubmissionRepository for upload ownership checks."""
    return PropertySubmissionRepository(db)


def get_s3_service() -> S3Service:
    """Provide S3Service configured from application settings."""
    return S3Service(get_settings())


def get_upload_service(
    repo: PropertySubmissionRepository = Depends(get_upload_repository),
    s3_service: S3Service = Depends(get_s3_service),
) -> UploadService:
    """Provide UploadService for presigned URL generation."""
    return UploadService(repository=repo, s3_service=s3_service, settings=get_settings())

