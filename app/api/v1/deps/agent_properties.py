"""Dependencies for agent property list routes."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_repository import PropertyRepository
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.services.agent_property_service import AgentPropertyService


def get_agent_property_service(db: Session = Depends(get_db)) -> AgentPropertyService:
    """Single DB session for both repositories (one request, one transaction scope)."""
    return AgentPropertyService(
        property_repository=PropertyRepository(db),
        submission_repository=PropertySubmissionRepository(db),
    )
