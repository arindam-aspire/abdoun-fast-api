"""Notification service (Phase 1 in-app notifications only)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
from sqlalchemy.exc import SQLAlchemyError

from fastapi import HTTPException

from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_template_service import NotificationTemplateService
from app.services.realtime_notification_service import RealtimeNotificationService
from app.utils.logger import api_logger
from app.utils.log_messages import format_log_message
from app.utils.status_codes import HTTPStatus


@dataclass(frozen=True, slots=True)
class NotificationCreateInput:
    recipient_user_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    type_key: str
    data: Mapping[str, Any] | None = None


class NotificationService:
    def __init__(
        self,
        repo: NotificationRepository,
        preference_service: NotificationPreferenceService,
        template_service: NotificationTemplateService,
        realtime_service: RealtimeNotificationService | None = None,
    ) -> None:
        self._repo = repo
        self._prefs = preference_service
        self._templates = template_service
        self._realtime = realtime_service

    def create_notification(self, *, input: NotificationCreateInput) -> Optional[Notification]:
        # Respect preferences (default enabled).
        if not self._prefs.is_enabled(user_id=input.recipient_user_id, notification_type=input.type_key):
            return None

        title, message = self._templates.build(type_key=input.type_key, data=input.data)
        row = Notification(
            recipient_user_id=input.recipient_user_id,
            actor_user_id=input.actor_user_id,
            type_key=input.type_key,
            title=title,
            message=message,
            data=dict(input.data) if input.data is not None else None,
            is_read=False,
        )
        self._repo.create(notification=row)
        self._repo.commit()
        self._repo.refresh(row)
        if self._realtime is not None:
            try:
                unread = self._repo.unread_count(user_id=row.recipient_user_id)
                self._realtime.notification_created(notification=row, unread_count=unread)
            except Exception:
                # Realtime is best-effort only.
                pass
        return row

    def list_notifications(
        self,
        *,
        current_user: User,
        page: int,
        page_size: int,
        include_archived: bool,
    ) -> tuple[Sequence[Notification], int]:
        offset = (max(1, page) - 1) * max(1, page_size)
        limit = max(1, page_size)
        return self._repo.list_for_user(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )

    def unread_count(self, *, current_user: User) -> int:
        return self._repo.unread_count(user_id=current_user.id)

    def mark_as_read(self, *, current_user: User, notification_id: uuid.UUID) -> bool:
        notif = self._repo.get_by_id(notification_id)
        if not notif or notif.archived_at is not None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Notification not found")
        self._enforce_ownership(current_user=current_user, notif=notif)
        changed = self._repo.mark_as_read(notification_id=notification_id, read_at=self._repo.now_utc())
        self._repo.commit()
        if changed and self._realtime is not None:
            try:
                self._repo.refresh(notif)
                unread = self._repo.unread_count(user_id=current_user.id)
                self._realtime.notification_read(notification=notif, unread_count=unread)
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
            except Exception:
                pass
        return changed

    def mark_all_as_read(self, *, current_user: User) -> int:
        updated = self._repo.mark_all_as_read(user_id=current_user.id, read_at=self._repo.now_utc())
        self._repo.commit()
        if updated and self._realtime is not None:
            try:
                unread = self._repo.unread_count(user_id=current_user.id)
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
            except Exception:
                pass
        return updated

    def archive(self, *, current_user: User, notification_id: uuid.UUID) -> bool:
        notif = self._repo.get_by_id(notification_id)
        if not notif:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Notification not found")
        self._enforce_ownership(current_user=current_user, notif=notif)
        if notif.archived_at is not None:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Notification already archived")
        changed = self._repo.archive(notification_id=notification_id, archived_at=self._repo.now_utc())
        self._repo.commit()
        if changed and self._realtime is not None:
            try:
                self._repo.refresh(notif)
                unread = self._repo.unread_count(user_id=current_user.id)
                self._realtime.notification_archived(notification=notif, unread_count=unread)
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
            except Exception:
                pass
        api_logger.info(
            format_log_message(
                "Notification archived user_id={user_id} notification_id={notification_id}",
                user_id=str(current_user.id),
                notification_id=str(notification_id),
            )
        )
        return changed

    def unarchive(self, *, current_user: User, notification_id: uuid.UUID) -> bool:
        notif = self._repo.get_by_id(notification_id)
        if not notif:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Notification not found")
        self._enforce_ownership(current_user=current_user, notif=notif)
        if notif.archived_at is None:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Notification is not archived")

        changed = self._repo.unarchive(notification_id=notification_id)
        self._repo.commit()
        if changed and self._realtime is not None:
            try:
                self._repo.refresh(notif)
                unread = self._repo.unread_count(user_id=current_user.id)
                self._realtime.notification_unarchived(notification=notif, unread_count=unread)
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
            except Exception:
                pass
        api_logger.info(
            format_log_message(
                "Notification unarchived user_id={user_id} notification_id={notification_id}",
                user_id=str(current_user.id),
                notification_id=str(notification_id),
            )
        )
        return changed

    def bulk_archive(self, *, current_user: User, notification_ids: Sequence[uuid.UUID]) -> tuple[int, list[uuid.UUID]]:
        if not notification_ids:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="notificationIds cannot be empty")

        rows = self._repo.list_by_ids(notification_ids=notification_ids)
        by_id = {n.id: n for n in rows}
        failed_ids: list[uuid.UUID] = []
        archive_ids: list[uuid.UUID] = []

        for nid in notification_ids:
            notif = by_id.get(nid)
            if not notif or notif.recipient_user_id != current_user.id or notif.archived_at is not None:
                failed_ids.append(nid)
                continue
            archive_ids.append(nid)

        try:
            affected_count = self._repo.archive_many(notification_ids=archive_ids, archived_at=self._repo.now_utc())
            self._repo.commit()
        except SQLAlchemyError as exc:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    "Notification bulk archive failed user_id={user_id} ids={ids} error={error}",
                    user_id=str(current_user.id),
                    ids=",".join(str(i) for i in notification_ids),
                    error=str(exc),
                )
            )
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Bulk archive failed")

        try:
            unread = self._repo.unread_count(user_id=current_user.id)
            if self._realtime is not None:
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
        except Exception:
            pass

        api_logger.info(
            format_log_message(
                "Notification bulk archive user_id={user_id} affected_count={affected_count} failed_count={failed_count}",
                user_id=str(current_user.id),
                affected_count=affected_count,
                failed_count=len(failed_ids),
            )
        )
        return affected_count, failed_ids

    def bulk_unarchive(self, *, current_user: User, notification_ids: Sequence[uuid.UUID]) -> tuple[int, list[uuid.UUID]]:
        if not notification_ids:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="notificationIds cannot be empty")

        rows = self._repo.list_by_ids(notification_ids=notification_ids)
        by_id = {n.id: n for n in rows}
        failed_ids: list[uuid.UUID] = []
        unarchive_ids: list[uuid.UUID] = []

        for nid in notification_ids:
            notif = by_id.get(nid)
            if not notif or notif.recipient_user_id != current_user.id or notif.archived_at is None:
                failed_ids.append(nid)
                continue
            unarchive_ids.append(nid)

        try:
            affected_count = self._repo.unarchive_many(notification_ids=unarchive_ids)
            self._repo.commit()
        except SQLAlchemyError as exc:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    "Notification bulk unarchive failed user_id={user_id} ids={ids} error={error}",
                    user_id=str(current_user.id),
                    ids=",".join(str(i) for i in notification_ids),
                    error=str(exc),
                )
            )
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Bulk unarchive failed")

        try:
            unread = self._repo.unread_count(user_id=current_user.id)
            if self._realtime is not None:
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
        except Exception:
            pass

        api_logger.info(
            format_log_message(
                "Notification bulk unarchive user_id={user_id} affected_count={affected_count} failed_count={failed_count}",
                user_id=str(current_user.id),
                affected_count=affected_count,
                failed_count=len(failed_ids),
            )
        )
        return affected_count, failed_ids

    def delete(self, *, current_user: User, notification_id: uuid.UUID) -> bool:
        """Hard delete a notification from database."""
        notif = self._repo.get_by_id(notification_id)
        if not notif:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Notification not found")
        self._enforce_ownership(current_user=current_user, notif=notif)

        try:
            changed = self._repo.hard_delete(notification_id=notification_id)
            self._repo.commit()
        except SQLAlchemyError as exc:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    "Notification delete failed user_id={user_id} notification_id={notification_id} error={error}",
                    user_id=str(current_user.id),
                    notification_id=str(notification_id),
                    error=str(exc),
                )
            )
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Notification delete failed")

        if changed and self._realtime is not None:
            try:
                unread = self._repo.unread_count(user_id=current_user.id)
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
            except Exception:
                pass
        api_logger.info(
            format_log_message(
                "Notification deleted user_id={user_id} notification_id={notification_id}",
                user_id=str(current_user.id),
                notification_id=str(notification_id),
            )
        )
        return changed

    def bulk_delete(self, *, current_user: User, notification_ids: Sequence[uuid.UUID]) -> tuple[int, list[uuid.UUID]]:
        if not notification_ids:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="notificationIds cannot be empty")

        rows = self._repo.list_by_ids(notification_ids=notification_ids)
        by_id = {n.id: n for n in rows}
        failed_ids: list[uuid.UUID] = []
        deletable_ids: list[uuid.UUID] = []

        for nid in notification_ids:
            notif = by_id.get(nid)
            if not notif:
                failed_ids.append(nid)
                continue
            if notif.recipient_user_id != current_user.id:
                failed_ids.append(nid)
                continue
            deletable_ids.append(nid)

        try:
            deleted_count = self._repo.hard_delete_many(notification_ids=deletable_ids)
            self._repo.commit()
        except SQLAlchemyError as exc:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    "Notification bulk delete failed user_id={user_id} ids={ids} error={error}",
                    user_id=str(current_user.id),
                    ids=",".join(str(i) for i in notification_ids),
                    error=str(exc),
                )
            )
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Bulk delete failed")

        try:
            unread = self._repo.unread_count(user_id=current_user.id)
            if self._realtime is not None:
                self._realtime.unread_count_updated(user_id=current_user.id, unread_count=unread)
        except Exception:
            pass

        api_logger.info(
            format_log_message(
                "Notification bulk delete user_id={user_id} deleted_count={deleted_count} failed_count={failed_count}",
                user_id=str(current_user.id),
                deleted_count=deleted_count,
                failed_count=len(failed_ids),
            )
        )
        return deleted_count, failed_ids

    @staticmethod
    def _enforce_ownership(*, current_user: User, notif: Notification) -> None:
        if notif.recipient_user_id != current_user.id:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")

