from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


DealClosureReviewAction = Literal["approve", "reject"]


class DealClosureCreate(BaseModel):
    property_hash: int | str
    lead_id: UUID | None = None
    reason: str | None = None


class DealClosureReview(BaseModel):
    action: DealClosureReviewAction
    reason: str | None = None

