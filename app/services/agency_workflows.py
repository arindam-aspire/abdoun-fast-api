from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.core.security import hash_secret, verify_secret
from app.models.live_schema import AgencyInvitation, AgencyMaster, PropertyListingSubmission, User, UserProfileChangeChallenge
from app.schemas.agents import normalize_phone
from app.schemas.agency import (
    AgencyInvitationAcceptRequest,
    AgencyInvitationCreateRequest,
    AgencyOfflineRegistrationRequest,
)
from app.services.audit import record_activity
from app.services.auth import cognito_service, create_user, find_user_by_username, register_cognito_user, serialize_agency
from app.services.notifications import send_email_notification
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_CONFLICT, STATUS_NOT_FOUND


PENDING_INVITATION = "PENDING"
INVITED = "INVITED"
ACCEPTED = "ACCEPTED"
EXPIRED = "EXPIRED"
REVOKED = "REVOKED"
PENDING_INVITATION_STATUSES = {PENDING_INVITATION, INVITED}

PENDING_APPROVAL = "PENDING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
ACTIVE = "ACTIVE"
INACTIVE = "INACTIVE"

PASSWORD_SETUP_PURPOSE = "password_setup"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_expired(expires_at: datetime) -> bool:
    current_time = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()
    return expires_at < current_time


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def ensure_agency_contact_available(db: Session, *, email: str, phone: str | None = None) -> None:
    normalized_email = _normalize_email(email)
    normalized_phone = normalize_phone(phone) if phone else ""
    match = AgencyMaster.email == normalized_email
    if normalized_phone:
        match = match | (AgencyMaster.phone == normalized_phone)
    existing = db.execute(select(AgencyMaster.email, AgencyMaster.phone).where(match)).all()
    if any(row.email == normalized_email for row in existing):
        raise HTTPException(status_code=STATUS_CONFLICT, detail="An agency with this email already exists")
    if normalized_phone and any(row.phone == normalized_phone for row in existing):
        raise HTTPException(status_code=STATUS_CONFLICT, detail="An agency with this phone number already exists")


def _token() -> str:
    return secrets.token_urlsafe(32)


def _frontend_base_url() -> str:
    return get_settings().frontend_base_url


def _agency_activation_link(token: str) -> str:
    return f"{_frontend_base_url()}/agency-password-setup?token={token}"


def _agency_invitation_link(token: str) -> str:
    return f"{_frontend_base_url()}/agency-invitation?token={token}"


def _expire_invitation_if_needed(db: Session, invitation: AgencyInvitation) -> AgencyInvitation:
    if invitation.status in PENDING_INVITATION_STATUSES and is_expired(invitation.expires_at):
        invitation.status = EXPIRED
        invitation.updated_at = utc_now()
        record_activity(
            db,
            activity_type="agency_invitation_expired",
            message=f"Agency invitation expired for {invitation.email}",
        )
    return invitation


def serialize_invitation(db: Session, invitation: AgencyInvitation) -> dict:
    _expire_invitation_if_needed(db, invitation)
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "agency_name": invitation.agency_name,
        "agency_trade_name": invitation.agency_trade_name,
        "phone": invitation.phone,
        "status": PENDING_INVITATION if invitation.status in PENDING_INVITATION_STATUSES else invitation.status,
        "invitation_link": _agency_invitation_link(invitation.token) if invitation.status in PENDING_INVITATION_STATUSES else None,
        "expires_at": _iso(invitation.expires_at),
        "accepted_at": _iso(invitation.accepted_at),
        "revoked_at": _iso(invitation.revoked_at),
        "created_at": _iso(invitation.created_at),
        "updated_at": _iso(invitation.updated_at),
    }


def create_agency_invitation(
    db: Session,
    *,
    payload: AgencyInvitationCreateRequest,
    invited_by: UUID,
) -> AgencyInvitation:
    email = _normalize_email(payload.email)
    ensure_agency_contact_available(db, email=email, phone=payload.phone or "")

    db.execute(
        select(AgencyInvitation)
        .where(AgencyInvitation.email == email, AgencyInvitation.status.in_(PENDING_INVITATION_STATUSES))
        .with_for_update()
    )
    for invitation in db.execute(
        select(AgencyInvitation).where(AgencyInvitation.email == email, AgencyInvitation.status.in_(PENDING_INVITATION_STATUSES))
    ).scalars().all():
        invitation.status = REVOKED
        invitation.revoked_by = invited_by
        invitation.revoked_at = utc_now()
        invitation.updated_at = utc_now()

    settings = get_settings()
    invitation = AgencyInvitation(
        id=uuid4(),
        email=email,
        agency_name=payload.agency_name,
        agency_trade_name=payload.agency_trade_name,
        phone=payload.phone,
        token=_token(),
        status=PENDING_INVITATION,
        invited_by=invited_by,
        expires_at=utc_now() + timedelta(seconds=settings.agency_invitation_ttl_seconds),
    )
    db.add(invitation)
    record_activity(
        db,
        activity_type="agency_invitation_sent",
        message=f"Agency invitation sent to {email}",
        user_id=invited_by,
    )
    send_email_notification(
        to_email=email,
        subject="Abdoun agency invitation",
        body=f"You have been invited to register your agency. Dev invitation link: {_agency_invitation_link(invitation.token)}",
    )
    return invitation


def get_invitation_by_token_or_404(db: Session, token: str) -> AgencyInvitation:
    invitation = db.execute(select(AgencyInvitation).where(AgencyInvitation.token == token)).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Invitation not found")
    return _expire_invitation_if_needed(db, invitation)


def revoke_agency_invitation(db: Session, *, invitation_id: UUID, actor_id: UUID) -> AgencyInvitation:
    invitation = db.get(AgencyInvitation, invitation_id)
    if not invitation:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Invitation not found")
    _expire_invitation_if_needed(db, invitation)
    if invitation.status not in PENDING_INVITATION_STATUSES:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Only active invitations can be revoked")
    invitation.status = REVOKED
    invitation.revoked_by = actor_id
    invitation.revoked_at = utc_now()
    invitation.updated_at = utc_now()
    record_activity(
        db,
        activity_type="agency_invitation_revoked",
        message=f"Agency invitation revoked for {invitation.email}",
        user_id=actor_id,
    )
    send_email_notification(
        to_email=invitation.email,
        subject="Abdoun agency invitation revoked",
        body="Your agency invitation has been revoked.",
    )
    return invitation


def create_agency_record(
    db: Session,
    *,
    agency_name: str,
    agency_trade_name: str,
    email: str,
    phone: str,
    legal_document_s3_link: str | None,
    status: str,
    website: str | None = None,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    zip_code: str | None = None,
    currency: str | None = None,
    measurement_unit: str | None = None,
) -> AgencyMaster:
    normalized_phone = normalize_phone(phone) if phone else phone
    ensure_agency_contact_available(db, email=email, phone=normalized_phone)
    agency = AgencyMaster(
        id=uuid4(),
        agency_name=agency_name,
        agency_trade_name=agency_trade_name,
        legal_document_s3_link=legal_document_s3_link or f"dev://agency-legal-documents/{uuid4()}/pending",
        email=_normalize_email(email),
        phone=normalized_phone or phone.strip(),
        website=website,
        address=address,
        city=city,
        state=state,
        country=country,
        zip_code=zip_code,
        is_active=status == ACTIVE,
        is_verified=status in {APPROVED, ACTIVE},
        status=status,
        currency=currency or get_settings().default_currency,
        measurement_unit=measurement_unit or get_settings().default_measurement_unit,
    )
    db.add(agency)
    try:
        db.flush()
    except IntegrityError as exc:
        error_text = str(getattr(exc, "orig", exc))
        if "uq_agency_master_email" in error_text:
            raise HTTPException(status_code=STATUS_CONFLICT, detail="An agency with this email already exists") from exc
        if "uq_agency_master_phone" in error_text:
            raise HTTPException(status_code=STATUS_CONFLICT, detail="An agency with this phone number already exists") from exc
        raise
    return agency


def create_agency_admin_user(db: Session, *, agency: AgencyMaster, password: str | None = None) -> User:
    return create_user(
        db,
        full_name=agency.agency_trade_name or agency.agency_name,
        email=agency.email,
        phone_number=agency.phone,
        password=password,
        role="admin",
        agency_id=agency.id,
    )


def create_password_setup_challenge(db: Session, *, user: User, agency: AgencyMaster, actor_id: UUID | None = None) -> str:
    settings = get_settings()
    token = _token()
    challenge = UserProfileChangeChallenge(
        id=uuid4(),
        user_id=user.id,
        purpose=PASSWORD_SETUP_PURPOSE,
        new_value=str(agency.id),
        otp_hash=hash_secret(token),
        expires_at=utc_now() + timedelta(seconds=settings.agency_password_setup_ttl_seconds),
    )
    db.add(challenge)
    record_activity(
        db,
        activity_type="agency_password_link_sent",
        message=f"Password creation link sent for agency {agency.id}",
        user_id=actor_id,
    )
    send_email_notification(
        to_email=user.email,
        subject="Create your Abdoun agency password",
        body=f"Create your agency password. Dev password setup link: {_agency_activation_link(token)}",
    )
    return token


def offline_register_agency(
    db: Session,
    *,
    payload: AgencyOfflineRegistrationRequest,
    actor_id: UUID,
) -> tuple[AgencyMaster, str | None]:
    agency = create_agency_record(
        db,
        agency_name=payload.agency_name,
        agency_trade_name=payload.agency_trade_name,
        email=payload.email,
        phone=payload.phone,
        legal_document_s3_link=payload.legal_document_s3_link,
        status=PENDING_APPROVAL,
        website=payload.website,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        zip_code=payload.zip_code,
        currency=payload.currency,
        measurement_unit=payload.measurement_unit,
    )
    user = create_agency_admin_user(db, agency=agency)
    user.is_active = False
    cognito_sub = register_cognito_user(
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone_number,
        on_existing="reuse",
        resolve_sub=True,
    )
    if cognito_sub:
        user.cognito_sub = cognito_sub
    record_activity(
        db,
        activity_type="agency_offline_registered",
        message=f"Agency {agency.id} created offline and pending verification",
        user_id=actor_id,
    )
    return agency, None


def accept_agency_invitation(db: Session, *, payload: AgencyInvitationAcceptRequest) -> AgencyMaster:
    invitation = get_invitation_by_token_or_404(db, payload.token)
    if invitation.status not in PENDING_INVITATION_STATUSES:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail=f"Invitation is {invitation.status.lower()}")
    agency = create_agency_record(
        db,
        agency_name=payload.agency_name,
        agency_trade_name=payload.agency_trade_name,
        email=invitation.email,
        phone=payload.phone,
        legal_document_s3_link=payload.legal_document_s3_link,
        status=PENDING_APPROVAL,
        website=payload.website,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        zip_code=payload.zip_code,
    )
    user = create_agency_admin_user(db, agency=agency)
    user.is_active = False
    invitation.status = ACCEPTED
    invitation.accepted_by = user.id
    invitation.accepted_at = utc_now()
    invitation.updated_at = utc_now()
    record_activity(
        db,
        activity_type="agency_invitation_accepted",
        message=f"Agency invitation accepted for {agency.email}",
        user_id=user.id,
    )
    send_email_notification(
        to_email=agency.email,
        subject="Agency registration submitted",
        body="Your agency registration has been submitted for Super Admin review.",
    )
    return agency


def approve_or_reject_agency(
    db: Session,
    *,
    agency: AgencyMaster,
    actor_id: UUID,
    action: str,
    reason: str | None = None,
) -> tuple[AgencyMaster, str | None]:
    normalized = action.strip().lower()
    if normalized == "approve":
        agency.status = APPROVED
        agency.is_verified = True
        agency.is_active = True
        user = find_user_by_username(db, agency.email)
        if not user:
            user = create_agency_admin_user(db, agency=agency)
        user.is_active = False
        token = create_password_setup_challenge(db, user=user, agency=agency, actor_id=actor_id)
        record_activity(db, activity_type="agency_registration_approved", message=f"Agency {agency.id} approved", user_id=actor_id)
        return agency, token
    if normalized == "reject":
        agency.status = REJECTED
        agency.is_verified = False
        agency.is_active = False
        record_activity(
            db,
            activity_type="agency_registration_rejected",
            message=f"Agency {agency.id} rejected: {reason or ''}",
            user_id=actor_id,
        )
        send_email_notification(
            to_email=agency.email,
            subject="Agency registration rejected",
            body=reason or "Your agency registration has been rejected.",
        )
        return agency, None
    raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid agency review action")


def resend_agency_password_setup(db: Session, *, agency: AgencyMaster, actor_id: UUID) -> str:
    if agency.status == ACTIVE:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency is already active; password link is not applicable")
    if agency.status != APPROVED:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency must be approved before password link can be sent")
    user = find_user_by_username(db, agency.email)
    if not user:
        user = create_agency_admin_user(db, agency=agency)
    user.is_active = False
    return create_password_setup_challenge(db, user=user, agency=agency, actor_id=actor_id)


def set_agency_activation(
    db: Session,
    *,
    agency: AgencyMaster,
    actor_id: UUID,
    is_active: bool,
) -> AgencyMaster:
    if is_active and not agency.is_verified:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency must be verified before activation")

    agency.is_active = is_active
    agency.status = ACTIVE if is_active else INACTIVE

    users = db.execute(select(User).where(User.agency_id == agency.id)).scalars().all()
    for user in users:
        user.is_active = is_active and bool(user.password_hash)

    if is_active:
        submissions = db.execute(
            select(PropertyListingSubmission).where(
                PropertyListingSubmission.agency_id == agency.id,
                PropertyListingSubmission.status == "deactivated",
            )
        ).scalars().all()
        for submission in submissions:
            payload = dict(submission.payload or {})
            agency_deactivation = payload.get("_agency_deactivation") or {}
            if agency_deactivation.get("deactivated_by_agency_id") != str(agency.id):
                continue
            previous_status = agency_deactivation.get("previous_status") or "active"
            submission.status = previous_status
            payload.pop("_agency_deactivation", None)
            submission.payload = payload
            flag_modified(submission, "payload")
    else:
        submissions = db.execute(
            select(PropertyListingSubmission).where(
                PropertyListingSubmission.agency_id == agency.id,
                PropertyListingSubmission.status == "active",
            )
        ).scalars().all()
        for submission in submissions:
            payload = dict(submission.payload or {})
            payload["_agency_deactivation"] = {
                "deactivated_by_agency_id": str(agency.id),
                "previous_status": submission.status,
                "deactivated_at": utc_now().isoformat(),
            }
            submission.status = "deactivated"
            submission.payload = payload
            flag_modified(submission, "payload")

    record_activity(
        db,
        activity_type="agency_activated" if is_active else "agency_deactivated",
        message=f"Agency {agency.id} {'activated' if is_active else 'deactivated'}",
        user_id=actor_id,
    )
    return agency


def complete_agency_password_setup(db: Session, *, token: str, password: str) -> AgencyMaster:
    challenges = db.execute(
        select(UserProfileChangeChallenge)
        .where(UserProfileChangeChallenge.purpose == PASSWORD_SETUP_PURPOSE)
        .order_by(UserProfileChangeChallenge.created_at.desc())
    ).scalars().all()
    challenge = next((item for item in challenges if verify_secret(token, item.otp_hash)), None)
    if not challenge:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Password creation link is invalid")
    if is_expired(challenge.expires_at):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Password creation link has expired")

    user = db.get(User, challenge.user_id)
    agency = db.get(AgencyMaster, UUID(str(challenge.new_value)))
    if not user or not agency:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Agency account not found")
    if agency.status not in {APPROVED, ACTIVE}:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Agency is not approved for password creation")

    user.password_hash = hash_secret(password)
    user.is_active = True
    if cognito_service.enabled and user.cognito_sub:
        cognito_service.admin_set_password(email=user.email, password=password)
    agency.status = ACTIVE
    agency.is_active = True
    agency.is_verified = True
    record_activity(
        db,
        activity_type="agency_activated",
        message=f"Agency {agency.id} activated",
        user_id=user.id,
    )
    send_email_notification(
        to_email=agency.email,
        subject="Agency account activated",
        body="Your agency account is active.",
    )
    return agency


def agency_response(agency: AgencyMaster, *, password_setup_token: str | None = None) -> dict:
    data = serialize_agency(agency)
    if data is not None:
        data["status"] = agency.status
    expose_password_link = password_setup_token and agency.status != ACTIVE
    return {
        "agency": data,
        "password_setup_token": password_setup_token if expose_password_link else None,
        "password_setup_link": _agency_activation_link(password_setup_token) if expose_password_link else None,
    }
