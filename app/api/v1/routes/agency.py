from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import false

from app.api.deps import DBSessionDep, RequestContext, require_any_role, require_authenticated_user
from app.models.live_schema import AgencyMaster
from app.schemas.agency import AgencyUpdateRequest, UploadRequest
from app.services.auth import create_otp_challenge, create_user, send_dev_otp, serialize_agency
from app.services.user_agencies import selectable_owner_agencies
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_FORBIDDEN, STATUS_NOT_FOUND

router = APIRouter()

AgencyAdminContext = Annotated[RequestContext, Depends(require_any_role("admin", "super_admin"))]
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def _role_names(context: RequestContext) -> set[str]:
    return {role.lower() for role in context.roles}


def _assert_can_access_agency(context: RequestContext, agency_id: UUID) -> None:
    roles = _role_names(context)
    if "super_admin" in roles:
        return
    if "admin" in roles and context.agency_id == agency_id:
        return
    raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Insufficient permissions")


@router.post("/register")
async def register_agency(
    db: DBSessionDep,
    agency_name: Annotated[str, Form()],
    agency_trade_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone_number: Annotated[str, Form()],
    password: Annotated[str, Form()],
    legal_document: Annotated[UploadFile, File()],
) -> dict:
    agency_id = uuid4()
    legal_document_url = f"dev://agency-legal-documents/{agency_id}/{legal_document.filename}"
    agency = AgencyMaster(
        id=agency_id,
        agency_name=agency_name,
        agency_trade_name=agency_trade_name,
        legal_document_s3_link=legal_document_url,
        email=email.strip().lower(),
        phone=phone_number,
        is_active=False,
        is_verified=False,
        currency="JOD",
        measurement_unit="sqm",
    )
    db.add(agency)
    db.flush()

    user = create_user(
        db,
        full_name=agency_trade_name or agency_name,
        email=email,
        phone_number=phone_number,
        password=password,
        role="admin",
        agency_id=agency.id,
    )
    _, otp = create_otp_challenge(
        db,
        user=user,
        purpose="signup_confirm",
        new_value=email.strip().lower(),
    )
    send_dev_otp(user=user, purpose="agency signup", otp=otp)
    db.commit()
    return success_response(
        {"agency": serialize_agency(agency), "otp": otp, "dev_email_otp": otp},
        "Agency registration submitted. Verification code logged in dev mode.",
    )


@router.get("/list")
def list_agencies(db: DBSessionDep, context: AuthenticatedContext, skip: int = 0, limit: int = 20) -> dict:
    roles = _role_names(context)
    query = db.query(AgencyMaster).order_by(AgencyMaster.created_at.desc())

    if "super_admin" in roles:
        pass
    elif "admin" in roles and context.agency_id:
        query = query.filter(AgencyMaster.id == context.agency_id)
    elif "admin" in roles:
        query = query.filter(false())
    else:
        agencies = selectable_owner_agencies(db, user_id=context.user_id)
        return success_response([serialize_agency(agency) for agency in agencies])

    agencies = query.offset(max(skip, 0)).limit(max(min(limit, 100), 1)).all()
    return success_response([serialize_agency(agency) for agency in agencies])


@router.get("/{agency_id}")
def get_agency(agency_id: UUID, db: DBSessionDep, context: AgencyAdminContext) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)
    return success_response(serialize_agency(agency))


@router.put("/{agency_id}")
def update_agency(
    agency_id: UUID,
    payload: AgencyUpdateRequest,
    db: DBSessionDep,
    context: AgencyAdminContext,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agency, field, value)

    db.commit()
    db.refresh(agency)
    return success_response({"agency": serialize_agency(agency), "legal_document_upload": None}, "Agency updated successfully")


@router.post("/{agency_id}/logo")
def request_agency_logo_upload(
    agency_id: UUID,
    payload: UploadRequest,
    db: DBSessionDep,
    context: AgencyAdminContext,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)
    agency.logo_url = f"dev://agency-logos/{agency.id}/{payload.file_name}"
    db.commit()
    return success_response({"upload_url": agency.logo_url}, "Agency logo upload URL generated")


@router.delete("/{agency_id}/logo")
def delete_agency_logo(agency_id: UUID, db: DBSessionDep, context: AgencyAdminContext) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)
    agency.logo_url = None
    db.commit()
    db.refresh(agency)
    return success_response(serialize_agency(agency), "Agency logo removed")


@router.post("/{agency_id}/legal-document")
def request_agency_legal_document_upload(
    agency_id: UUID,
    payload: UploadRequest,
    db: DBSessionDep,
    context: AgencyAdminContext,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)
    agency.legal_document_s3_link = f"dev://agency-legal-documents/{agency.id}/{payload.file_name}"
    db.commit()
    return success_response({"upload_url": agency.legal_document_s3_link}, "Agency legal document upload URL generated")
