"""Repository for property listing submission workflow persistence."""

import uuid
from typing import Any, ClassVar, List, Tuple
from contextlib import nullcontext

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.models.owner import Owner, PropertyOwner
from app.models.property_listing_submission import PropertyListingSubmission
from app.models.property_normalized import (
    Area,
    City,
    Feature,
    PropertyFeature,
    PropertyMedia,
    PropertyNormalized,
    PropertyTranslation,
    PropertyStatus,
    PropertyType,
)
from app.models.user import User


class PropertySubmissionRepository:
    """Persistence operations for property submission workflow."""

    # Rows visible on the admin moderation list (excludes agent-only ``draft`` / ``in_progress``).
    ADMIN_VISIBLE_SUBMISSION_STATUSES: ClassVar[tuple[str, ...]] = (
        "submitted",
        "changes_requested",
        "approved",
        "rejected",
    )

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_submission(self, submission: PropertyListingSubmission) -> PropertyListingSubmission:
        self._db.add(submission)
        return submission

    def get_submission_by_id(
        self,
        submission_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> PropertyListingSubmission | None:
        filters = [PropertyListingSubmission.id == submission_id]
        if not include_deleted:
            filters.append(PropertyListingSubmission.deleted_at.is_(None))
        stmt = select(PropertyListingSubmission).where(and_(*filters))
        return self._db.execute(stmt).scalar_one_or_none()

    def list_admin_submissions(
        self,
        *,
        status: str | None,
        page: int,
        limit: int,
        include_deleted: bool = False,
    ) -> list[
        tuple[
            PropertyListingSubmission,
            str | None,
            int | None,
            str | None,
            str | None,
            uuid.UUID | None,
        ]
    ]:
        """Paginated rows for the admin moderation queue (excludes ``draft`` / ``in_progress``)."""
        stmt = (
            select(
                PropertyListingSubmission,
                User.full_name,
                PropertyNormalized.property_hash,
                PropertyNormalized.title,
                PropertyNormalized.reference_number,
                PropertyNormalized.agent_user_id,
            )
            .where(PropertyListingSubmission.status.in_(self.ADMIN_VISIBLE_SUBMISSION_STATUSES))
            .join(User, User.id == PropertyListingSubmission.submitted_by)
            .outerjoin(PropertyNormalized, PropertyNormalized.id == PropertyListingSubmission.property_id)
            .order_by(PropertyListingSubmission.updated_at.desc())
        )
        if not include_deleted:
            stmt = stmt.where(PropertyListingSubmission.deleted_at.is_(None))
        if status:
            stmt = stmt.where(PropertyListingSubmission.status == status)
        offset = max(page - 1, 0) * limit
        stmt = stmt.offset(offset).limit(limit)
        return list(self._db.execute(stmt).all())

    def count_admin_submissions(self, *, status: str | None, include_deleted: bool = False) -> int:
        stmt = select(func.count(PropertyListingSubmission.id)).where(
            PropertyListingSubmission.status.in_(self.ADMIN_VISIBLE_SUBMISSION_STATUSES)
        )
        if not include_deleted:
            stmt = stmt.where(PropertyListingSubmission.deleted_at.is_(None))
        if status:
            stmt = stmt.where(PropertyListingSubmission.status == status)
        return int(self._db.execute(stmt).scalar() or 0)

    def list_submissions_linked_to_properties(
        self,
        *,
        user_id: uuid.UUID,
        property_ids: List[uuid.UUID],
    ) -> dict[uuid.UUID, PropertyListingSubmission]:
        """Latest submission row per property for this submitter (ordered by updated_at desc)."""
        if not property_ids:
            return {}
        stmt = (
            select(PropertyListingSubmission)
            .where(
                PropertyListingSubmission.submitted_by == user_id,
                PropertyListingSubmission.property_id.is_not(None),
                PropertyListingSubmission.property_id.in_(property_ids),
                PropertyListingSubmission.deleted_at.is_(None),
            )
            .order_by(PropertyListingSubmission.updated_at.desc())
        )
        rows: List[PropertyListingSubmission] = list(self._db.execute(stmt).scalars().all())
        by_property: dict[uuid.UUID, PropertyListingSubmission] = {}
        for row in rows:
            pid = row.property_id
            if pid is not None and pid not in by_property:
                by_property[pid] = row
        return by_property

    def list_draft_submissions_without_property(
        self,
        *,
        user_id: uuid.UUID,
        limit: int,
    ) -> Tuple[List[PropertyListingSubmission], int]:
        """Draft / in-progress submissions with no property row yet (wizard not submitted)."""
        statuses = ("draft", "in_progress")
        filters = (
            PropertyListingSubmission.submitted_by == user_id,
            PropertyListingSubmission.property_id.is_(None),
            PropertyListingSubmission.status.in_(statuses),
            PropertyListingSubmission.deleted_at.is_(None),
        )
        count_stmt = select(func.count(PropertyListingSubmission.id)).where(*filters)
        total = int(self._db.execute(count_stmt).scalar() or 0)
        stmt = (
            select(PropertyListingSubmission)
            .where(*filters)
            .order_by(PropertyListingSubmission.updated_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        rows = list(self._db.execute(stmt).scalars().all())
        return rows, total

    def get_category_type(self, type_id: int) -> PropertyType | None:
        stmt = select(PropertyType).where(PropertyType.id == type_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_city(self, city_id: int) -> City | None:
        stmt = select(City).where(City.id == city_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_area(self, area_id: int) -> Area | None:
        stmt = select(Area).where(Area.id == area_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def count_existing_features(self, feature_ids: list[int]) -> int:
        if not feature_ids:
            return 0
        stmt = select(Feature.id).where(Feature.id.in_(feature_ids))
        return len(self._db.execute(stmt).scalars().all())

    def get_property(self, property_id: uuid.UUID, *, include_deleted: bool = False) -> PropertyNormalized | None:
        filters = [PropertyNormalized.id == property_id]
        if not include_deleted:
            filters.append(PropertyNormalized.deleted_at.is_(None))
        stmt = select(PropertyNormalized).where(and_(*filters))
        return self._db.execute(stmt).scalar_one_or_none()

    def get_property_status_by_slug(self, slug: str) -> PropertyStatus | None:
        """Look up a property_status row by slug (case-sensitive; slugs are stored lower)."""
        stmt = select(PropertyStatus).where(PropertyStatus.slug == slug)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_owner_by_email_or_phone(
        self,
        email: str | None,
        phone: str | None,
        *,
        for_update: bool = False,
    ) -> Owner | None:
        """Find an existing owner by exact email first, otherwise phone."""
        if email:
            stmt = select(Owner).where(Owner.email == email)
            if for_update:
                stmt = stmt.with_for_update()
            owner = self._db.execute(stmt).scalar_one_or_none()
            if owner is not None:
                return owner
        if phone:
            stmt = select(Owner).where(Owner.phone == phone)
            if for_update:
                stmt = stmt.with_for_update()
            owner = self._db.execute(stmt).scalar_one_or_none()
            if owner is not None:
                return owner
        return None

    def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
        return self._db.execute(stmt).scalar_one_or_none()

    def get_user_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone_number == phone, User.deleted_at.is_(None))
        return self._db.execute(stmt).scalar_one_or_none()

    def add_owner(self, owner: Owner) -> Owner:
        self._db.add(owner)
        return owner

    def add_property_owner(self, mapping: PropertyOwner) -> PropertyOwner:
        self._db.add(mapping)
        return mapping

    def add_property_feature(self, property_feature: PropertyFeature) -> PropertyFeature:
        self._db.add(property_feature)
        return property_feature

    def add_property_media(self, media: PropertyMedia) -> PropertyMedia:
        self._db.add(media)
        return media

    def replace_property_owners(self, property_id: uuid.UUID) -> None:
        self._db.execute(delete(PropertyOwner).where(PropertyOwner.property_id == property_id))

    def replace_property_features(self, property_id: uuid.UUID) -> None:
        self._db.execute(delete(PropertyFeature).where(PropertyFeature.property_id == property_id))

    def replace_property_media(self, property_id: uuid.UUID) -> None:
        self._db.execute(delete(PropertyMedia).where(PropertyMedia.property_id == property_id))

    def create_property(self, property_obj: PropertyNormalized) -> PropertyNormalized:
        self._db.add(property_obj)
        return property_obj

    def flush(self) -> None:
        self._db.flush()

    def refresh(self, instance: Any) -> None:
        self._db.refresh(instance)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def begin_transaction(self):
        """Open a DB transaction scope for multi-step submit operations."""
        # Session may already be in an implicit transaction (autobegin) after reads.
        # In that case, reuse current transaction scope instead of nesting begin().
        if self._db.in_transaction():
            return nullcontext()
        return self._db.begin()

    def delete_submission_and_property(self, *, submission: PropertyListingSubmission) -> None:
        """Remove linked ``properties_normalized`` row (if any) and the submission. Caller must commit.

        Child rows (property_owner, property_features, property_media) are cleared first; other
        references use DB-level CASCADE or SET NULL (e.g. user_property_favorites, leads).
        """
        if submission.property_id is not None:
            pid = submission.property_id
            self.replace_property_owners(pid)
            self.replace_property_features(pid)
            self.replace_property_media(pid)
            self._db.execute(delete(PropertyTranslation).where(PropertyTranslation.property_id == pid))
            self._db.execute(delete(PropertyNormalized).where(PropertyNormalized.id == pid))
        self._db.delete(submission)
