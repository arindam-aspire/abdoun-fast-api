"""Dependencies for lead routes."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.notifications import get_notification_event_emitter
from app.db.session import get_db
from app.repositories.lead_repository import LeadRepository
from app.services.lead_audit_service import LeadAuditService
from app.services.lead_notification_service import LeadNotificationService
from app.services.lead_permission_service import LeadPermissionService
from app.services.lead_service import LeadService
from app.services.lead_workflow_manager import LeadWorkflowManager
from app.services.notification_event_emitter import NotificationEventEmitter


def get_lead_repository(db: Session = Depends(get_db)) -> LeadRepository:
    return LeadRepository(db)


def get_lead_service(
    repo: LeadRepository = Depends(get_lead_repository),
    notification_emitter: NotificationEventEmitter = Depends(get_notification_event_emitter),
) -> LeadService:
    workflow = LeadWorkflowManager()
    permission = LeadPermissionService(repo)
    audit = LeadAuditService(repo)
    notifications = LeadNotificationService()
    return LeadService(
        repo=repo,
        workflow=workflow,
        permission=permission,
        audit=audit,
        notifications=notifications,
        notification_emitter=notification_emitter,
    )
