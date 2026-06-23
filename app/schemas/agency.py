from __future__ import annotations

from pydantic import BaseModel


class AgencyUpdateRequest(BaseModel):
    agency_name: str | None = None
    agency_trade_name: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    currency: str | None = None
    measurement_unit: str | None = None


class UploadRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int
