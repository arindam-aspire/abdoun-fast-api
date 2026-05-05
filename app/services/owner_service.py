"""Business logic for owner and property-owner mapping CRUD with error handling."""
import uuid
from typing import List

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.owner import Owner, PropertyOwner
from app.domains.shared.pagination import calculate_pagination
from app.repositories.owner_repository import OwnerRepository
from app.schemas.owner import (
    OwnerCreate,
    OwnerListResponse,
    OwnerResponse,
    OwnerUpdate,
    OwnerWithMappingsResponse,
    PropertyOwnerCreate,
    PropertyOwnerResponse,
    PropertyOwnerUpdate,
)
from app.utils.status_codes import HTTPStatus


class OwnerService:
    """Service layer for owner and property-owner operations."""

    def __init__(self, repository: OwnerRepository) -> None:
        self._repo = repository

    def list_owners(self, *, page: int, page_size: int) -> OwnerListResponse:
        safe_page = max(1, int(page))
        safe_page_size = max(1, int(page_size))
        offset = (safe_page - 1) * safe_page_size
        owners = self._repo.list_owners(limit=safe_page_size, offset=offset)
        total = self._repo.count_owners()
        meta = calculate_pagination(page=safe_page, page_size=safe_page_size, total=total)
        return OwnerListResponse(
            items=[OwnerResponse.model_validate(owner) for owner in owners],
            total=total,
            page=meta.page,
            pageSize=meta.page_size,
            totalPages=meta.total_pages,
            hasNext=meta.has_next,
            hasPrevious=meta.has_previous,
        )

    def get_owner(self, owner_id: uuid.UUID) -> OwnerWithMappingsResponse:
        owner = self._repo.get_owner_by_id(owner_id)
        if not owner:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Owner not found")
        mappings = self._repo.list_mappings_by_owner_id(owner_id)
        return OwnerWithMappingsResponse(
            owner=OwnerResponse.model_validate(owner),
            mappings=[PropertyOwnerResponse.model_validate(item) for item in mappings],
        )

    def create_owner(self, body: OwnerCreate) -> OwnerResponse:
        if body.email:
            existing = self._repo.get_owner_by_email(body.email)
            if existing:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Owner with this email already exists",
                )
        owner = Owner(
            full_name=body.full_name,
            email=body.email,
            phone=body.phone,
            nationality=body.nationality,
            ssi=body.ssi,
            address=body.address,
            documents=[doc.model_dump(mode="json") for doc in body.documents],
        )
        try:
            self._repo.create_owner(owner)
            self._repo.commit()
            self._repo.refresh(owner)
            return OwnerResponse.model_validate(owner)
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to create owner",
            )

    def update_owner(self, owner_id: uuid.UUID, body: OwnerUpdate) -> OwnerResponse:
        owner = self._repo.get_owner_by_id(owner_id)
        if not owner:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Owner not found")

        updates = body.model_dump(exclude_unset=True)
        if "documents" in updates and updates["documents"] is not None:
            updates["documents"] = [doc.model_dump(mode="json") for doc in updates["documents"]]

        for field, value in updates.items():
            setattr(owner, field, value)

        try:
            self._repo.commit()
            self._repo.refresh(owner)
            return OwnerResponse.model_validate(owner)
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to update owner",
            )

    def delete_owner(self, owner_id: uuid.UUID) -> bool:
        owner = self._repo.get_owner_by_id(owner_id)
        if not owner:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Owner not found")
        try:
            self._repo.delete_owner(owner)
            self._repo.commit()
            return True
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to delete owner",
            )

    def create_property_owner_mapping(self, body: PropertyOwnerCreate) -> PropertyOwnerResponse:
        existing = self._repo.get_mapping(property_id=body.property_id, owner_id=body.owner_id)
        if existing:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Property-owner mapping already exists",
            )

        mapping = PropertyOwner(
            property_id=body.property_id,
            owner_id=body.owner_id,
            is_active=body.is_active,
        )
        try:
            self._repo.create_mapping(mapping)
            self._repo.commit()
            self._repo.refresh(mapping)
            return PropertyOwnerResponse.model_validate(mapping)
        except IntegrityError:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid property_id or owner_id",
            )
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to create property-owner mapping",
            )

    def update_property_owner_mapping(
        self, mapping_id: uuid.UUID, body: PropertyOwnerUpdate
    ) -> PropertyOwnerResponse:
        mapping = self._repo.get_mapping_by_id(mapping_id)
        if not mapping:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Property-owner mapping not found",
            )
        mapping.is_active = body.is_active
        try:
            self._repo.commit()
            self._repo.refresh(mapping)
            return PropertyOwnerResponse.model_validate(mapping)
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to update property-owner mapping",
            )

    def delete_property_owner_mapping(self, mapping_id: uuid.UUID) -> bool:
        mapping = self._repo.get_mapping_by_id(mapping_id)
        if not mapping:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Property-owner mapping not found",
            )
        try:
            self._repo.delete_mapping(mapping)
            self._repo.commit()
            return True
        except Exception:
            self._repo.rollback()
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to delete property-owner mapping",
            )
