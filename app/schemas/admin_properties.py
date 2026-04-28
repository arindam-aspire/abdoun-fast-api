"""Schemas for admin property management endpoints (assign agent, etc.)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AdminAssignAgentToPropertyRequest(BaseModel):
    """Assign an agent user to an existing property."""

    agent_id: uuid.UUID | None = Field(
        default=None,
        description="Agent user id to assign; null to unassign the current agent.",
    )


class AdminAssignAgentToPropertyResponse(BaseModel):
    """Assignment result payload."""

    property_id: uuid.UUID
    agent_id: uuid.UUID | None = None

