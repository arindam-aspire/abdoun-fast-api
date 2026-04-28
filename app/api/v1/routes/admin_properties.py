"""Admin endpoints for property management (assignment to agents, etc.)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.admin_properties import get_property_admin_service
from app.api.v1.deps.security import require_role
from app.models.user import User
from app.schemas.admin_properties import (
    AdminAssignAgentToPropertyRequest,
    AdminAssignAgentToPropertyResponse,
)
from app.services.property_admin_service import PropertyAdminService
from app.utils.constants import UserRoles
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.patch(
    "/properties/{property_id}/assign-agent",
    response_model=StandardResponse[AdminAssignAgentToPropertyResponse],
)
def assign_agent_to_property(
    property_id: uuid.UUID,
    body: AdminAssignAgentToPropertyRequest,
    current_user: Annotated[User, require_role(UserRoles.ADMIN)],
    service: Annotated[PropertyAdminService, Depends(get_property_admin_service)],
):
    """Assign (or unassign) an agent to a property.

    This is intentionally separate from the property creation flow:
    admins are not treated as agents; assignment can happen later.
    """
    pid, aid = service.assign_agent_to_property(
        property_id=property_id,
        agent_id=body.agent_id,
        admin_user_id=current_user.id,
    )
    return create_success_response(
        data=AdminAssignAgentToPropertyResponse(property_id=pid, agent_id=aid),
        message=None,
    )

