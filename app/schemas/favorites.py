from __future__ import annotations

from pydantic import BaseModel


class FavoriteCreate(BaseModel):
    property_hash: int


class RecentViewCreate(BaseModel):
    property_hash_id: int

