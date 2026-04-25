"""Dependency providers for platform admin dashboard."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.admin_dashboard_repository import AdminDashboardRepository
from app.services.admin_dashboard_service import AdminDashboardService


def get_admin_dashboard_repository(db: Session = Depends(get_db)) -> AdminDashboardRepository:
    return AdminDashboardRepository(db)


def get_admin_dashboard_service(
    repo: AdminDashboardRepository = Depends(get_admin_dashboard_repository),
) -> AdminDashboardService:
    return AdminDashboardService(repo)
