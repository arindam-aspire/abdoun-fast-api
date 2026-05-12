"""Dependencies for notification routes (Phase 1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.notification_repository import NotificationRepository
from app.repositories.notification_preferences_repository import NotificationPreferencesRepository
from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_event_emitter import NotificationEventEmitter
from app.services.notification_service import NotificationService
from app.services.notification_template_service import NotificationTemplateService
from app.services.realtime_notification_service import RealtimeNotificationService
from app.websockets.connection_manager import connection_manager


DBSessionDep = Annotated[Session, Depends(get_db)]


def get_notification_repository(db: DBSessionDep) -> NotificationRepository:
    return NotificationRepository(db)


def get_notification_preferences_repository(db: DBSessionDep) -> NotificationPreferencesRepository:
    return NotificationPreferencesRepository(db)


def get_notification_template_service() -> NotificationTemplateService:
    return NotificationTemplateService()


def get_realtime_notification_service() -> RealtimeNotificationService:
    # Single-instance, in-memory only (no Redis / brokers in this phase).
    return RealtimeNotificationService(connection_manager)


def get_notification_preference_service(
    repo: NotificationPreferencesRepository = Depends(get_notification_preferences_repository),
) -> NotificationPreferenceService:
    return NotificationPreferenceService(repo)


def get_notification_service(
    repo: NotificationRepository = Depends(get_notification_repository),
    prefs: NotificationPreferenceService = Depends(get_notification_preference_service),
    templates: NotificationTemplateService = Depends(get_notification_template_service),
    realtime: RealtimeNotificationService = Depends(get_realtime_notification_service),
) -> NotificationService:
    return NotificationService(
        repo=repo,
        preference_service=prefs,
        template_service=templates,
        realtime_service=realtime,
    )


def get_notification_event_emitter(
    svc: NotificationService = Depends(get_notification_service),
) -> NotificationEventEmitter:
    return NotificationEventEmitter(notification_service=svc)

