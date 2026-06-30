from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import false

from app.api.deps import DBSessionDep, RequestContext, require_any_role, require_authenticated_user
from app.models.live_schema import AgencyMaster
from app.schemas.agency import (
    AgencyInvitationAcceptRequest,
    AgencyInvitationCreateRequest,
    AgencyOfflineRegistrationRequest,
    AgencyPasswordSetupRequest,
    OwnerAgencyAssignmentRequest,
    AgencyReviewRequest,
    AgencyUpdateRequest,
    UploadRequest,
)
from app.services.agency_workflows import (
    accept_agency_invitation,
    agency_response,
    approve_or_reject_agency,
    complete_agency_password_setup,
    create_agency_invitation,
    get_invitation_by_token_or_404,
    offline_register_agency,
    resend_agency_password_setup,
    revoke_agency_invitation,
    serialize_invitation,
    PENDING_APPROVAL,
)
from app.services.auth import create_otp_challenge, create_user, send_dev_otp, serialize_agency
from app.services.owners import assign_owner_to_agency, list_agency_owners, list_platform_owners
from app.services.user_agencies import selectable_owner_agencies
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_FORBIDDEN, STATUS_NOT_FOUND

router = APIRouter()

AgencyAdminContext = Annotated[RequestContext, Depends(require_any_role("admin", "super_admin"))]
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]
SuperAdminContext = Annotated[RequestContext, Depends(require_any_role("super_admin"))]


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
    legal_document: Annotated[UploadFile, File()],
    password: Annotated[str | None, Form()] = None,
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
        status=PENDING_APPROVAL,
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
        password=None,
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


@router.post("/offline-registration")
def create_offline_agency(
    payload: AgencyOfflineRegistrationRequest,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    agency, password_setup_token = offline_register_agency(db, payload=payload, actor_id=context.user_id)
    db.commit()
    db.refresh(agency)
    return success_response(
        agency_response(agency, password_setup_token=password_setup_token),
        "Agency created and password creation link logged in dev mode.",
    )


@router.post("/invitations")
def invite_agency(
    payload: AgencyInvitationCreateRequest,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    invitation = create_agency_invitation(db, payload=payload, invited_by=context.user_id)
    db.commit()
    db.refresh(invitation)
    return success_response(serialize_invitation(db, invitation), "Agency invitation logged in dev mode")


@router.get("/invitations/validate")
def validate_agency_invitation(token: str, db: DBSessionDep) -> dict:
    invitation = get_invitation_by_token_or_404(db, token)
    db.commit()
    return success_response(serialize_invitation(db, invitation))


@router.post("/invitations/accept")
def accept_invited_agency(payload: AgencyInvitationAcceptRequest, db: DBSessionDep) -> dict:
    agency = accept_agency_invitation(db, payload=payload)
    db.commit()
    db.refresh(agency)
    return success_response(agency_response(agency), "Agency registration submitted for approval")


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invited_agency(invitation_id: UUID, context: SuperAdminContext, db: DBSessionDep) -> dict:
    invitation = revoke_agency_invitation(db, invitation_id=invitation_id, actor_id=context.user_id)
    db.commit()
    db.refresh(invitation)
    return success_response(serialize_invitation(db, invitation), "Agency invitation revoked")


@router.post("/password/setup")
def setup_agency_password(payload: AgencyPasswordSetupRequest, db: DBSessionDep) -> dict:
    agency = complete_agency_password_setup(db, token=payload.token, password=payload.password)
    db.commit()
    db.refresh(agency)
    return success_response(agency_response(agency), "Agency activated successfully")


@router.get("/list")
def list_agencies(db: DBSessionDep, context: AuthenticatedContext, skip: int = 0, limit: int = 20) -> dict:
    roles = _role_names(context)
    query = db.query(AgencyMaster).order_by(AgencyMaster.created_at.desc())
    normalized_skip = max(skip, 0)
    normalized_limit = max(min(limit, 100), 1)

    if "super_admin" in roles:
        pass
    elif "admin" in roles and context.agency_id:
        query = query.filter(AgencyMaster.id == context.agency_id)
    elif "admin" in roles:
        query = query.filter(false())
    else:
        agencies = selectable_owner_agencies(db, user_id=context.user_id)
        total = len(agencies)
        page_items = agencies[normalized_skip : normalized_skip + normalized_limit]
        return success_response(
            [serialize_agency(agency) for agency in page_items],
            meta={
                "pagination": {
                    "total": total,
                    "skip": normalized_skip,
                    "limit": normalized_limit,
                }
            },
        )

    total = query.count()
    agencies = query.offset(normalized_skip).limit(normalized_limit).all()
    return success_response(
        [serialize_agency(agency) for agency in agencies],
        meta={
            "pagination": {
                "total": total,
                "skip": normalized_skip,
                "limit": normalized_limit,
            }
        },
    )


@router.get("/{agency_id}/owners")
def get_agency_owners(
    agency_id: UUID,
    db: DBSessionDep,
    context: AgencyAdminContext,
    page: int = 1,
    pageSize: int = 10,
    search: str | None = None,
    status: str | None = None,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)
    items, pagination = list_agency_owners(
        db,
        agency_id=agency_id,
        page=page,
        page_size=pageSize,
        search=search,
        status=status,
    )
    return success_response({**pagination, "items": items}, meta={"pagination": pagination})


@router.get("/owners")
def get_platform_owners(
    db: DBSessionDep,
    context: SuperAdminContext,
    page: int = 1,
    pageSize: int = 10,
    search: str | None = None,
    status: str | None = None,
    agencyId: UUID | None = None,
) -> dict:
    items, pagination = list_platform_owners(
        db,
        page=page,
        page_size=pageSize,
        search=search,
        status=status,
        agency_id=agencyId,
    )
    return success_response({**pagination, "items": items}, meta={"pagination": pagination})


@router.post("/owners/{owner_id}/agency")
def assign_owner_agency(
    owner_id: UUID,
    payload: OwnerAgencyAssignmentRequest,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    mapping = assign_owner_to_agency(
        db,
        owner_id=owner_id,
        agency_id=payload.agency_id,
        actor_user_id=context.user_id,
    )
    db.commit()
    db.refresh(mapping)
    return success_response(
        {
            "id": str(mapping.id),
            "owner_id": str(mapping.user_id),
            "agency_id": str(mapping.agency_id),
            "relationship_type": mapping.relationship_type,
            "status": mapping.status,
            "is_primary": mapping.is_primary,
        },
        "Owner agency assignment updated",
    )


@router.get("/{agency_id}")
def get_agency(agency_id: UUID, db: DBSessionDep, context: AgencyAdminContext) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)
    return success_response(serialize_agency(agency))


@router.post("/{agency_id}/review")
def review_agency_registration(
    agency_id: UUID,
    payload: AgencyReviewRequest,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    agency, password_setup_token = approve_or_reject_agency(
        db,
        agency=agency,
        actor_id=context.user_id,
        action=payload.action,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(agency)
    message = "Agency approved and password creation link logged in dev mode" if password_setup_token else "Agency rejected"
    return success_response(agency_response(agency, password_setup_token=password_setup_token), message)


@router.post("/{agency_id}/password-link")
def resend_agency_password_link(
    agency_id: UUID,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    password_setup_token = resend_agency_password_setup(db, agency=agency, actor_id=context.user_id)
    db.commit()
    db.refresh(agency)
    return success_response(
        agency_response(agency, password_setup_token=password_setup_token),
        "Password creation link logged in dev mode",
    )


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
