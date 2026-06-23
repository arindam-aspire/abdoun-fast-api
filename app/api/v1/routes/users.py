from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.models.live_schema import AgencyMaster
from app.schemas.users import AssignUserAgencyRequest
from app.services.auth import get_user_or_404, serialize_user
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_NOT_FOUND

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.patch("/agency")
def assign_user_agency(payload: AssignUserAgencyRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    user = get_user_or_404(db, context.user_id)
    agency_id = UUID(payload.agencyId)
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")

    user.agency_id = agency.id
    db.commit()
    db.refresh(user)
    return success_response(serialize_user(db, user), "Agency assigned successfully")
