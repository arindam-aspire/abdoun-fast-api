"""Repository layer for owner and property-owner persistence operations."""
import uuid
from typing import List, Optional

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.owner import Owner, PropertyOwner


class OwnerRepository:
    """Repository for Owner and PropertyOwner CRUD."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_owners(self, *, limit: int, offset: int) -> List[Owner]:
        stmt: Select = select(Owner).order_by(Owner.created_at.desc()).offset(offset).limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def count_owners(self) -> int:
        stmt: Select = select(func.count(Owner.owner_id))
        return int(self._db.execute(stmt).scalar() or 0)

    def get_owner_by_id(self, owner_id: uuid.UUID) -> Optional[Owner]:
        stmt = select(Owner).where(Owner.owner_id == owner_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_owner_by_email(self, email: str) -> Optional[Owner]:
        stmt = select(Owner).where(Owner.email == email)
        return self._db.execute(stmt).scalar_one_or_none()

    def create_owner(self, owner: Owner) -> Owner:
        self._db.add(owner)
        return owner

    def delete_owner(self, owner: Owner) -> None:
        self._db.delete(owner)

    def get_mapping_by_id(self, mapping_id: uuid.UUID) -> Optional[PropertyOwner]:
        stmt = select(PropertyOwner).where(PropertyOwner.id == mapping_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_mapping(
        self,
        *,
        property_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Optional[PropertyOwner]:
        stmt = select(PropertyOwner).where(
            and_(PropertyOwner.property_id == property_id, PropertyOwner.owner_id == owner_id)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_mappings_by_owner_id(self, owner_id: uuid.UUID) -> List[PropertyOwner]:
        stmt = select(PropertyOwner).where(PropertyOwner.owner_id == owner_id)
        return list(self._db.execute(stmt).scalars().all())

    def create_mapping(self, mapping: PropertyOwner) -> PropertyOwner:
        self._db.add(mapping)
        return mapping

    def delete_mapping(self, mapping: PropertyOwner) -> None:
        self._db.delete(mapping)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def refresh(self, instance: object) -> None:
        self._db.refresh(instance)
