from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import false, or_

from app.api.deps import DBSessionDep, RequestContext, require_any_role, require_authenticated_user
from app.models.live_schema import AgencyMaster
from app.schemas.agency import (
    AgencyActivationRequest,
    AgencyInvitationAcceptRequest,
    AgencyInvitationCreateRequest,
    AgencyOfflineRegistrationRequest,
    AgencyPasswordSetupRequest,
    OwnerAgencyAssignmentRequest,
    AgencyReviewRequest,
    AgencyUpdateRequest,
    UploadRequest,
)
from app.schemas.agents import validate_e164_phone
from app.schemas.owners import OwnerStatusUpdateRequest, OwnerUpdateRequest
from app.services.agency_workflows import (
    accept_agency_invitation,
    agency_response,
    approve_or_reject_agency,
    complete_agency_password_setup,
    create_agency_invitation,
    ensure_agency_contact_available,
    get_invitation_by_token_or_404,
    offline_register_agency,
    resend_agency_password_setup,
    revoke_agency_invitation,
    serialize_invitation,
    set_agency_activation,
    PENDING_APPROVAL,
)
from app.services.auth import (
    build_otp_response_data,
    create_otp_challenge,
    create_user,
    otp_delivery_message,
    send_dev_otp,
    serialize_agency,
)
from app.services.owners import (
    assign_owner_to_agency,
    get_owner,
    list_agency_owners,
    list_platform_owners,
    update_owner,
    update_owner_status,
)
from app.services.user_agencies import selectable_owner_agencies
from app.core.config import get_settings
from app.services.media_urls import (
    canonicalize_media_url,
    generate_presigned_put_url,
    probe_s3_object_access,
    resolve_readable_media_url,
)
from app.utils.api_response import raise_api_error, success_response
from app.utils.status_codes import (
    STATUS_BAD_REQUEST,
    STATUS_FORBIDDEN,
    STATUS_INTERNAL_SERVER_ERROR,
    STATUS_NOT_FOUND,
    STATUS_UNAUTHORIZED,
)

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


def _actor_user_id(context: RequestContext) -> UUID:
    if context.user_id is None:
        raise_api_error(
            status_code=STATUS_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Authentication is required",
        )
    return context.user_id


def _agency_s3_upload(prefix: str, owner_id: UUID, payload: UploadRequest) -> dict:
    safe_file_name = PurePosixPath(payload.file_name).name
    object_key = f"{prefix}/{owner_id}/{uuid4()}-{safe_file_name}"
    content_type = (payload.content_type or "").strip()
    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    if bucket:
        presigned = generate_presigned_put_url(object_key)
        if not presigned:
            raise_api_error(
                status_code=STATUS_INTERNAL_SERVER_ERROR,
                code="UPLOAD_ERROR",
                message="Could not generate upload URL",
            )
        return presigned
    dev_url = f"dev://uploads/{object_key}"
    return {
        "upload_url": dev_url,
        "object_key": object_key,
        "file_url": dev_url,
        "readable_url": dev_url,
        "signed_read_url": dev_url,
        "upload_http_method": "PUT",
        "view_http_method": "GET",
    }


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
    normalized_phone = validate_e164_phone(phone_number, field_name="phone_number")
    ensure_agency_contact_available(db, email=email, phone=normalized_phone)
    agency_id = uuid4()
    legal_document_url = f"dev://agency-legal-documents/{agency_id}/{legal_document.filename}"
    agency = AgencyMaster(
        id=agency_id,
        agency_name=agency_name,
        agency_trade_name=agency_trade_name,
        legal_document_s3_link=legal_document_url,
        email=email.strip().lower(),
        phone=normalized_phone,
        is_active=False,
        is_verified=False,
        status=PENDING_APPROVAL,
        currency=get_settings().default_currency,
        measurement_unit=get_settings().default_measurement_unit,
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
    challenge, otp = create_otp_challenge(
        db,
        user=user,
        purpose="signup_confirm",
        new_value=email.strip().lower(),
    )
    send_dev_otp(user=user, purpose="agency signup", otp=otp, challenge=challenge)
    db.commit()
    return success_response(
        build_otp_response_data(agency=serialize_agency(agency)),
        otp_delivery_message(
            fallback_dev_message="Agency registration submitted. Verification code logged in dev mode.",
            sent_message="Agency registration submitted. Verification code sent.",
        ),
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
        "Agency created and submitted for verification.",
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
def list_agencies(
    db: DBSessionDep,
    context: AuthenticatedContext,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    agencyStatus: str | None = None,
    verificationStatus: str | None = None,
    sortBy: str = "created_at",
    sortOrder: str = "desc",
) -> dict:
    roles = _role_names(context)
    query = db.query(AgencyMaster)
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
        if search:
            term = search.strip().lower()
            agencies = [
                agency
                for agency in agencies
                if term in (agency.agency_name or "").lower()
                or term in (agency.agency_trade_name or "").lower()
                or term in (agency.email or "").lower()
                or term in (agency.phone or "").lower()
            ]
        if agencyStatus:
            requested_active = agencyStatus.strip().lower() == "active"
            agencies = [agency for agency in agencies if bool(agency.is_active) is requested_active]
        if verificationStatus:
            normalized_verification = verificationStatus.strip().lower().replace("_", " ")
            if normalized_verification == "verified":
                agencies = [agency for agency in agencies if bool(agency.is_verified)]
            elif normalized_verification == "rejected":
                agencies = [agency for agency in agencies if getattr(agency, "status", "") == "REJECTED"]
            elif normalized_verification in {"pending verification", "pending"}:
                agencies = [
                    agency
                    for agency in agencies
                    if not agency.is_verified and getattr(agency, "status", "") != "REJECTED"
                ]
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

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AgencyMaster.agency_name.ilike(term),
                AgencyMaster.agency_trade_name.ilike(term),
                AgencyMaster.email.ilike(term),
                AgencyMaster.phone.ilike(term),
            )
        )
    if agencyStatus:
        normalized_agency_status = agencyStatus.strip().lower()
        if normalized_agency_status == "active":
            query = query.filter(AgencyMaster.is_active.is_(True))
        elif normalized_agency_status == "inactive":
            query = query.filter(AgencyMaster.is_active.is_(False), AgencyMaster.status != "PENDING_APPROVAL")
        elif normalized_agency_status in {"pending", "pending_approval"}:
            query = query.filter(AgencyMaster.status == "PENDING_APPROVAL")
        elif normalized_agency_status == "approved":
            query = query.filter(AgencyMaster.status == "APPROVED")
        elif normalized_agency_status == "rejected":
            query = query.filter(AgencyMaster.status == "REJECTED")
    if verificationStatus:
        normalized_verification = verificationStatus.strip().lower().replace("_", " ")
        if normalized_verification == "verified":
            query = query.filter(AgencyMaster.is_verified.is_(True))
        elif normalized_verification == "rejected":
            query = query.filter(AgencyMaster.status == "REJECTED")
        elif normalized_verification in {"pending verification", "pending"}:
            query = query.filter(AgencyMaster.is_verified.is_(False), AgencyMaster.status != "REJECTED")

    sortable_columns = {
        "created_at": AgencyMaster.created_at,
        "agency_name": AgencyMaster.agency_name,
        "email": AgencyMaster.email,
        "status": AgencyMaster.status,
    }
    sort_column = sortable_columns.get(sortBy, AgencyMaster.created_at)
    query = query.order_by(sort_column.asc() if sortOrder.strip().lower() == "asc" else sort_column.desc())

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


@router.get("/owners/{owner_id}")
def get_owner_details(
    owner_id: UUID,
    db: DBSessionDep,
    context: AgencyAdminContext,
) -> dict:
    owner = get_owner(
        db,
        owner_id=owner_id,
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
    )
    return success_response(owner)


@router.patch("/owners/{owner_id}")
def patch_owner_details(
    owner_id: UUID,
    payload: OwnerUpdateRequest,
    db: DBSessionDep,
    context: AgencyAdminContext,
) -> dict:
    if payload.full_name is None and payload.email is None and payload.phone_number is None:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="At least one field is required to update",
        )
    owner = update_owner(
        db,
        owner_id=owner_id,
        actor_user_id=_actor_user_id(context),
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
    )
    db.commit()
    return success_response(owner, "Owner updated successfully")


@router.patch("/owners/{owner_id}/status")
def set_owner_status(
    owner_id: UUID,
    payload: OwnerStatusUpdateRequest,
    db: DBSessionDep,
    context: AgencyAdminContext,
) -> dict:
    owner = update_owner_status(
        db,
        owner_id=owner_id,
        actor_user_id=_actor_user_id(context),
        actor_roles=context.roles,
        actor_agency_id=context.agency_id,
        status=payload.status,
        reason=payload.reason,
        legacy_status_label=True,
    )
    db.commit()
    status = str(owner.get("status") or "").upper()
    if status == "ACTIVE":
        message = "Owner activated successfully"
    elif status == "SUSPENDED":
        message = "Owner deactivated successfully"
    else:
        message = f"Owner status updated to {status}"
    return success_response(owner, message)


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


@router.post("/{agency_id}/activation")
def update_agency_activation(
    agency_id: UUID,
    payload: AgencyActivationRequest,
    context: SuperAdminContext,
    db: DBSessionDep,
) -> dict:
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    agency = set_agency_activation(
        db,
        agency=agency,
        actor_id=context.user_id,
        is_active=payload.is_active,
    )
    db.commit()
    db.refresh(agency)
    message = "Agency activated" if agency.is_active else "Agency deactivated"
    return success_response(agency_response(agency), message)


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
    upload = _agency_s3_upload("agency_logo", agency.id, payload)
    agency.logo_url = upload["file_url"]
    db.commit()
    return success_response(
        {
            "upload_url": upload["upload_url"],
            "object_key": upload["object_key"],
            "file_url": upload["file_url"],
            "readable_url": upload["readable_url"],
            "signed_read_url": upload["signed_read_url"],
        },
        "Agency logo upload URL generated",
    )


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


@router.get("/{agency_id}/legal-document")
def get_agency_legal_document_url(agency_id: UUID, db: DBSessionDep, context: AgencyAdminContext) -> dict:
    """Return a fresh GET-presigned URL for the stored agency legal document."""
    agency = db.get(AgencyMaster, agency_id)
    if not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency not found")
    _assert_can_access_agency(context, agency_id)

    stored = (agency.legal_document_s3_link or "").strip()
    if not stored:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Legal document not found")

    canonical = canonicalize_media_url(stored) or stored
    readable = resolve_readable_media_url(canonical)
    if not readable:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Could not resolve legal document URL")

    probe_s3_object_access(canonical)
    settings = get_settings()
    return success_response(
        {
            "file_url": canonical,
            "readable_url": readable,
            "signed_read_url": readable,
            "http_method": "GET",
        },
        "Agency legal document URL generated",
        meta={"expires_in": settings.media_url_presign_expires_seconds, "http_method": "GET"},
    )


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
    upload = _agency_s3_upload("agency_legal_document", agency.id, payload)
    agency.legal_document_s3_link = upload["file_url"]
    db.commit()
    return success_response(
        {
            "upload_url": upload["upload_url"],
            "object_key": upload["object_key"],
            "file_url": upload["file_url"],
            "readable_url": upload["readable_url"],
            "signed_read_url": upload["signed_read_url"],
            "upload_http_method": "PUT",
            "view_http_method": "GET",
        },
        "Agency legal document upload URL generated",
    )
