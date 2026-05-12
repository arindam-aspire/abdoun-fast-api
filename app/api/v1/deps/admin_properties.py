"""Dependencies for admin property endpoints."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.notifications import get_notification_event_emitter
from app.db.session import get_db
from app.repositories.property_admin_repository import PropertyAdminRepository
from app.services.notification_event_emitter import NotificationEventEmitter
from app.services.property_admin_service import PropertyAdminService


def get_property_admin_service(
    db: Session = Depends(get_db),
    notification_emitter: NotificationEventEmitter = Depends(get_notification_event_emitter),
) -> PropertyAdminService:
    return PropertyAdminService(
        PropertyAdminRepository(db),
        notification_emitter=notification_emitter,
    )

