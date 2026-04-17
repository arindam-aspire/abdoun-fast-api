"""Pydantic schemas for owner and property-owner mapping CRUD."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OwnerDocument(BaseModel):
    documentType: str
    fileName: str
    fileKey: str
    uploadedAt: datetime


class OwnerBase(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    nationality: str | None = Field(default=None, max_length=100)
    ssi: str | None = Field(default=None, max_length=50)
    address: str | None = None
    documents: list[OwnerDocument] = Field(default_factory=list)


class OwnerCreate(OwnerBase):
    pass


class OwnerUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    nationality: str | None = Field(default=None, max_length=100)
    ssi: str | None = Field(default=None, max_length=50)
    address: str | None = None
    documents: list[OwnerDocument] | None = None


class OwnerResponse(OwnerBase):
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PropertyOwnerCreate(BaseModel):
    property_id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool = False


class PropertyOwnerUpdate(BaseModel):
    is_active: bool


class PropertyOwnerResponse(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OwnerWithMappingsResponse(BaseModel):
    owner: OwnerResponse
    mappings: list[PropertyOwnerResponse]


OwnerDocumentPayload = dict[str, Any]
