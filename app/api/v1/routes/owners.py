"""Owner and property-owner mapping CRUD endpoints."""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps.owners import get_owner_service
from app.domains.shared.pagination import calculate_pagination
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
from app.services.owner_service import OwnerService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.post("", response_model=StandardResponse[OwnerResponse])
def create_owner(
    body: OwnerCreate,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Create owner with optional documents metadata."""
    owner = service.create_owner(body)
    return create_success_response(data=owner, message="Owner created successfully")


@router.get("", response_model=StandardResponse[OwnerListResponse])
def list_owners(
    service: Annotated[OwnerService, Depends(get_owner_service)],
    page: Annotated[int, Query(ge=1, description="1-based page index.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize", description="Items per page.")] = 50,
):
    """List owners with canonical page-based pagination."""
    owners = service.list_owners(page=page, page_size=page_size)
    pm = calculate_pagination(page=owners.page, page_size=owners.pageSize, total=owners.total)
    return create_success_response(data=owners, message=None, pagination=pm)


@router.get("/{owner_id}", response_model=StandardResponse[OwnerWithMappingsResponse])
def get_owner(
    owner_id: uuid.UUID,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Get owner details and attached property mappings."""
    owner = service.get_owner(owner_id)
    return create_success_response(data=owner, message=None)


@router.patch("/{owner_id}", response_model=StandardResponse[OwnerResponse])
def update_owner(
    owner_id: uuid.UUID,
    body: OwnerUpdate,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Update owner fields and documents."""
    owner = service.update_owner(owner_id, body)
    return create_success_response(data=owner, message="Owner updated successfully")


@router.delete("/{owner_id}", response_model=StandardResponse[bool])
def delete_owner(
    owner_id: uuid.UUID,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Delete owner and related mappings."""
    deleted = service.delete_owner(owner_id)
    return create_success_response(data=deleted, message="Owner deleted successfully")


@router.post("/property-mappings", response_model=StandardResponse[PropertyOwnerResponse])
def create_property_owner_mapping(
    body: PropertyOwnerCreate,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Create mapping between owner and property."""
    mapping = service.create_property_owner_mapping(body)
    return create_success_response(data=mapping, message="Property-owner mapping created successfully")


@router.patch("/property-mappings/{mapping_id}", response_model=StandardResponse[PropertyOwnerResponse])
def update_property_owner_mapping(
    mapping_id: uuid.UUID,
    body: PropertyOwnerUpdate,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Update property-owner mapping status."""
    mapping = service.update_property_owner_mapping(mapping_id, body)
    return create_success_response(data=mapping, message="Property-owner mapping updated successfully")


@router.delete("/property-mappings/{mapping_id}", response_model=StandardResponse[bool])
def delete_property_owner_mapping(
    mapping_id: uuid.UUID,
    service: Annotated[OwnerService, Depends(get_owner_service)],
):
    """Delete property-owner mapping."""
    deleted = service.delete_property_owner_mapping(mapping_id)
    return create_success_response(data=deleted, message="Property-owner mapping deleted successfully")
