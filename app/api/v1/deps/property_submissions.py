"""Dependency providers for property submission routes."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.services.property_submission_service import PropertySubmissionService


def get_property_submission_repository(db: Session = Depends(get_db)) -> PropertySubmissionRepository:
    """Provide PropertySubmissionRepository for request-scoped DB session."""
    return PropertySubmissionRepository(db)


def get_property_submission_service(
    repo: PropertySubmissionRepository = Depends(get_property_submission_repository),
) -> PropertySubmissionService:
    """Provide PropertySubmissionService for list-your-property workflow."""
    return PropertySubmissionService(repo)
