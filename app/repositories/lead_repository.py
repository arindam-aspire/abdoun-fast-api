"""Repository for lead lifecycle persistence and scope-aware queries."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.models.property_normalized import Lead, LeadMessage, LeadNote, LeadStatusHistory, PropertyNormalized
from app.models.user import Role, User
from app.services.translation_service import get_title_description_for_language


def _title_to_slug(raw_title: str | None) -> str | None:
    if not raw_title or not str(raw_title).strip():
        return None
    t = str(raw_title).strip().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = t.strip("-")
    return t or None


def _legacy_thumbnail_url(raw_images: Any) -> Optional[str]:
    images: list[Any] = []
    if isinstance(raw_images, str):
        try:
            images = json.loads(raw_images)
        except Exception:
            images = []
    elif isinstance(raw_images, list):
        images = raw_images
    first = next((str(url).strip() for url in images if url and str(url).strip()), None)
    return first or None


def _property_thumbnail_url(prop: PropertyNormalized) -> Optional[str]:
    media_rows = list(getattr(prop, "__dict__", {}).get("media_items") or [])
    image_rows = [
        row
        for row in media_rows
        if (getattr(row, "media_type", "image") or "image").strip().lower() == "image"
    ]
    image_rows.sort(key=lambda row: (not bool(getattr(row, "is_primary", False)), getattr(row, "display_order", 0) or 0))
    for row in image_rows:
        url = getattr(row, "thumb_url", None) or getattr(row, "url", None)
        if url and str(url).strip():
            return str(url).strip()
    return _legacy_thumbnail_url(getattr(prop, "images", None))


def _normalize_phone_for_match(value: str | None) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    prefix = "+" if raw.startswith("+") else ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"{prefix}{digits}" if digits else ""


def _normalize_property_name_for_match(value: str | None) -> str:
    return str(value or "").strip().lower()


class LeadRepository:
    """Persistence/query layer for lead workflows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_property_listing_agent_id(self, *, property_id: UUID) -> Optional[UUID]:
        stmt = select(PropertyNormalized.agent_user_id).where(PropertyNormalized.id == property_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_property_id_by_hash(self, *, property_hash: int) -> Optional[UUID]:
        stmt = (
            select(PropertyNormalized.id)
            .where(PropertyNormalized.property_hash == property_hash)
            .where(PropertyNormalized.deleted_at.is_(None))
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def create_lead(self, *, lead: Lead) -> Lead:
        self._db.add(lead)
        self._db.flush()
        return lead

    def list_active_user_ids_with_role(self, *, role_name: str) -> list[UUID]:
        """Distinct active, non-deleted user IDs that have the given role name."""
        stmt = (
            select(User.id)
            .join(User.roles)
            .where(Role.name == role_name)
            .where(User.deleted_at.is_(None))
            .where(User.is_active.is_(True))
            .distinct()
        )
        return list(self._db.scalars(stmt).all())

    def get_role_names_by_user_ids(self, user_ids: set[UUID]) -> dict[UUID, set[str]]:
        """Role names per user for notification routing (single query)."""
        if not user_ids:
            return {}
        stmt = select(User).options(selectinload(User.roles)).where(User.id.in_(user_ids))
        rows = list(self._db.execute(stmt).scalars().unique().all())
        return {user.id: {r.name for r in (user.roles or [])} for user in rows}

    def find_duplicate_offline_lead(
        self,
        *,
        phone_number: str,
        property_id: Optional[UUID] = None,
        property_name: Optional[str] = None,
    ) -> Optional[Lead]:
        normalized_phone = _normalize_phone_for_match(phone_number)
        normalized_property_name = _normalize_property_name_for_match(property_name)
        property_filters = []
        if property_id:
            property_filters.append(Lead.property_id == property_id)
        if normalized_property_name:
            property_filters.append(func.lower(func.trim(Lead.external_property_name)) == normalized_property_name)
        if not normalized_phone or not property_filters:
            return None

        phone_expr = func.regexp_replace(func.coalesce(Lead.external_owner_phone, ""), "[^0-9+]", "", "g")
        stmt = (
            select(Lead)
            .where(Lead.status != "CLOSED")
            .where(phone_expr == normalized_phone)
            .where(or_(*property_filters))
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def allocate_next_lead_number(self) -> str:
        """Atomically allocate next display lead number for current UTC year (LD-YYYY-NNNNNN)."""
        now = datetime.now(timezone.utc)
        year = now.year
        sql = text(
            """
            INSERT INTO lead_number_counters (year, last_value)
            VALUES (:year, 1)
            ON CONFLICT (year) DO UPDATE
            SET last_value = lead_number_counters.last_value + 1
            RETURNING last_value
            """
        )
        seq = int(self._db.execute(sql, {"year": year}).scalar_one())
        return f"LD-{year}-{seq:06d}"

    def get_property_summaries_by_ids(self, property_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        if not property_ids:
            return {}
        unique = list(dict.fromkeys(property_ids))
        stmt = (
            select(PropertyNormalized)
            .options(selectinload(PropertyNormalized.translations), selectinload(PropertyNormalized.media_items))
            .where(PropertyNormalized.id.in_(unique))
        )
        rows = list(self._db.execute(stmt).scalars().unique().all())
        out: dict[UUID, dict[str, Any]] = {}
        for prop in rows:
            title, _desc = get_title_description_for_language(prop, None)
            t = (title or "").strip() or None
            ph = getattr(prop, "property_hash", None)
            out[prop.id] = {
                "id": str(prop.id),
                "title": t,
                "slug": _title_to_slug(t),
                "thumbnailUrl": _property_thumbnail_url(prop),
                "propertyHash": int(ph) if ph is not None else None,
            }
        return out

    def get_agent_summaries_by_ids(self, agent_ids: set[UUID]) -> dict[UUID, dict[str, Any]]:
        if not agent_ids:
            return {}
        stmt = select(User).where(User.id.in_(agent_ids))
        rows = list(self._db.execute(stmt).scalars().all())
        return {
            user.id: {
                "id": str(user.id),
                "fullName": user.full_name,
                "email": user.email,
                "phone": user.phone_number,
            }
            for user in rows
        }

    def get_user_summaries_by_ids(self, user_ids: set[UUID]) -> dict[UUID, dict[str, Any]]:
        if not user_ids:
            return {}
        stmt = select(User).where(User.id.in_(user_ids))
        rows = list(self._db.execute(stmt).scalars().all())
        return {
            user.id: {
                "id": str(user.id),
                "fullName": user.full_name,
                "email": user.email,
                "phone": user.phone_number,
            }
            for user in rows
        }

    def get_lead_by_id(self, *, lead_id: UUID) -> Optional[Lead]:
        stmt = select(Lead).where(Lead.id == lead_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def list_agent_leads(
        self,
        *,
        agent_id: UUID,
        status: Optional[str],
        source: Optional[str],
        limit: int,
        offset: int,
    ) -> tuple[list[Lead], int]:
        stmt = select(Lead).where(Lead.assigned_agent_id == agent_id)
        count_stmt = select(func.count(Lead.id)).where(Lead.assigned_agent_id == agent_id)
        if status:
            stmt = stmt.where(Lead.status == status)
            count_stmt = count_stmt.where(Lead.status == status)
        if source:
            stmt = stmt.where(Lead.source == source)
            count_stmt = count_stmt.where(Lead.source == source)
        stmt = stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        items = list(self._db.execute(stmt).scalars().all())
        total = int(self._db.execute(count_stmt).scalar() or 0)
        return items, total

    def list_admin_leads(
        self,
        *,
        status: Optional[str],
        source: Optional[str],
        limit: int,
        offset: int,
    ) -> tuple[list[Lead], int]:
        stmt = select(Lead)
        count_stmt = select(func.count(Lead.id))
        if status:
            stmt = stmt.where(Lead.status == status)
            count_stmt = count_stmt.where(Lead.status == status)
        if source:
            stmt = stmt.where(Lead.source == source)
            count_stmt = count_stmt.where(Lead.source == source)
        stmt = stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        items = list(self._db.execute(stmt).scalars().all())
        total = int(self._db.execute(count_stmt).scalar() or 0)
        return items, total

    def list_user_leads(
        self,
        *,
        user_id: UUID,
        status: Optional[str],
        source: Optional[str],
        limit: int,
        offset: int,
    ) -> tuple[list[Lead], int]:
        stmt = select(Lead).where(Lead.user_id == user_id)
        count_stmt = select(func.count(Lead.id)).where(Lead.user_id == user_id)
        if status:
            stmt = stmt.where(Lead.status == status)
            count_stmt = count_stmt.where(Lead.status == status)
        if source:
            stmt = stmt.where(Lead.source == source)
            count_stmt = count_stmt.where(Lead.source == source)
        stmt = stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        items = list(self._db.execute(stmt).scalars().all())
        total = int(self._db.execute(count_stmt).scalar() or 0)
        return items, total

    def get_lead_status_summary(
        self,
        *,
        scope: str,
        actor_id: Optional[UUID] = None,
        source: Optional[str] = None,
    ) -> dict[str, int]:
        statuses = ("NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED")
        stmt = select(Lead.status, func.count(Lead.id)).group_by(Lead.status)
        if scope == "agent":
            stmt = stmt.where(Lead.assigned_agent_id == actor_id)
        elif scope == "user":
            stmt = stmt.where(Lead.user_id == actor_id)
        elif scope != "admin":
            return {"total": 0, **{status: 0 for status in statuses}}
        if source:
            stmt = stmt.where(Lead.source == source)
        rows = self._db.execute(stmt).all()
        summary = {status: 0 for status in statuses}
        for status, count in rows:
            key = str(status)
            if key in summary:
                summary[key] = int(count or 0)
        return {"total": sum(summary.values()), **summary}

    def add_status_history(
        self,
        *,
        lead_id: UUID,
        from_status: Optional[str],
        to_status: str,
        actor_user_id: Optional[UUID],
        actor_role: Optional[str],
        reason: Optional[str] = None,
    ) -> LeadStatusHistory:
        row = LeadStatusHistory(
            lead_id=lead_id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def list_status_history(self, *, lead_id: UUID) -> list[LeadStatusHistory]:
        stmt = (
            select(LeadStatusHistory)
            .where(LeadStatusHistory.lead_id == lead_id)
            .order_by(LeadStatusHistory.changed_at.asc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def create_note(self, *, lead_id: UUID, author_user_id: UUID, note: str) -> LeadNote:
        row = LeadNote(lead_id=lead_id, author_user_id=author_user_id, note=note)
        self._db.add(row)
        self._db.flush()
        return row

    def get_note(self, *, note_id: UUID) -> Optional[LeadNote]:
        stmt = select(LeadNote).where(LeadNote.id == note_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def list_notes(self, *, lead_id: UUID) -> list[LeadNote]:
        stmt = select(LeadNote).where(LeadNote.lead_id == lead_id).order_by(LeadNote.created_at.desc())
        return list(self._db.execute(stmt).scalars().all())

    def delete_note(self, *, note: LeadNote) -> None:
        self._db.delete(note)

    def create_message(
        self,
        *,
        lead_id: UUID,
        sender_user_id: UUID,
        recipient_user_id: Optional[UUID],
        message: str,
        channel: str = "IN_APP",
        delivery_state: Optional[str] = None,
    ) -> LeadMessage:
        row = LeadMessage(
            lead_id=lead_id,
            sender_user_id=sender_user_id,
            recipient_user_id=recipient_user_id,
            message=message,
            channel=channel,
            delivery_state=delivery_state,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def list_messages(self, *, lead_id: UUID) -> list[LeadMessage]:
        stmt = select(LeadMessage).where(LeadMessage.lead_id == lead_id).order_by(LeadMessage.created_at.asc())
        return list(self._db.execute(stmt).scalars().all())

    def find_recent_duplicate_contact_form_lead(
        self,
        *,
        property_id: UUID,
        user_id: UUID,
        message: str,
        dedupe_window_minutes: int = 2,
    ) -> Optional[Lead]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=dedupe_window_minutes)
        stmt = (
            select(Lead)
            .where(
                Lead.property_id == property_id,
                Lead.user_id == user_id,
                Lead.source == "EMAIL_FORM",
                Lead.message == message,
                Lead.created_at >= cutoff,
            )
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def unpublish_property_on_lead_close(
        self,
        *,
        property_id: UUID,
        actor_user_id: UUID,
        reason: str = "Lead closed",
    ) -> None:
        stmt = select(PropertyNormalized).where(PropertyNormalized.id == property_id)
        prop = self._db.execute(stmt).scalar_one_or_none()
        if prop is None:
            return
        prop.deleted_at = datetime.now(timezone.utc)
        prop.deleted_by = actor_user_id
        prop.delete_reason = reason

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
