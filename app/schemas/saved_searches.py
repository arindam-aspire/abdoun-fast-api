from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    search_criteria: dict[str, Any] = Field(default_factory=dict)
    notification_enabled: bool = False


class SavedSearchUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    search_criteria: dict[str, Any] = Field(default_factory=dict)

