"""Dependencies for agent routes: repository and service injection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.agent_repository import AgentRepository
from app.services.agent_service import AgentService


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_agent_repository(db: DBSessionDep) -> AgentRepository:
    """FastAPI dependency that provides an AgentRepository instance."""
    return AgentRepository(db)


def get_agent_service(
    repo: AgentRepository = Depends(get_agent_repository),
) -> AgentService:
    """FastAPI dependency that provides an AgentService instance."""
    return AgentService(repo)
