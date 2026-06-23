from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.live_schema import ActivityLog


def record_activity(
    db: Session,
    *,
    activity_type: str,
    message: str,
    user_id: UUID | None = None,
    property_id: UUID | None = None,
    tone: str | None = None,
) -> ActivityLog:
    activity = ActivityLog(
        id=uuid4(),
        user_id=user_id,
        property_id=property_id,
        activity_type=activity_type,
        message=message,
        tone=tone,
    )
    db.add(activity)
    return activity
