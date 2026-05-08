"""Dependencies for agent routes: repository and service injection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.agent_repository import AgentRepository
from app.services.agent_service import AgentService
from app.api.v1.deps.notifications import get_notification_service
from app.services.notification_service import NotificationService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_agent_repository(db: DBSessionDep) -> AgentRepository:
    """Provide an AgentRepository bound to the request database session.

    Args:
        db: Injected database session (from get_db).

    Returns:
        AgentRepository instance for agent routes.
    """
    return AgentRepository(db)


def get_agent_service(
    repo: AgentRepository = Depends(get_agent_repository),
    notification_service: NotificationService = Depends(get_notification_service),
) -> AgentService:
    """Provide an AgentService for invite, onboarding, and admin CRUD.

    Args:
        repo: Injected AgentRepository (from get_agent_repository).

    Returns:
        AgentService instance.
    """
    return AgentService(repo, notification_service)
