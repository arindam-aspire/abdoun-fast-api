"""Dependency providers for agent dashboard summary endpoint."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.agent_dashboard_repository import AgentDashboardRepository
from app.services.agent_dashboard_service import AgentDashboardService


def get_agent_dashboard_repository(db: Session = Depends(get_db)) -> AgentDashboardRepository:
    """Provide an AgentDashboardRepository bound to request DB session."""
    return AgentDashboardRepository(db)


def get_agent_dashboard_service(
    repo: AgentDashboardRepository = Depends(get_agent_dashboard_repository),
) -> AgentDashboardService:
    """Provide an AgentDashboardService for dashboard summary endpoint."""
    return AgentDashboardService(repo)

