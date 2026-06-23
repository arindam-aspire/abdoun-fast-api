from __future__ import annotations

from pydantic import BaseModel


class AssignUserAgencyRequest(BaseModel):
    agencyId: str
