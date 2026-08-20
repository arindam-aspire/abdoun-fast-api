from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_secret, verify_secret
from app.core.tokens import create_token, verify_token
from app.models.live_schema import (
    AgencyMaster,
    AgentProfile,
    Permission,
    Role,
    RolePermission,
    User,
    UserProfileChangeChallenge,
    UserRole,
)
from app.services.media_urls import with_readable_media_urls
from app.services.notifications import send_email_notification, send_sms_notification
from app.services.notifications.email.templates import build_otp_verification_email
from app.services.user_agencies import (
    REL_AGENCY_ADMIN,
    REL_AGENT,
    REL_PROPERTY_OWNER,
    active_mappings,
    ensure_user_agency_mapping,
    primary_agency_id_for_context,
)
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_CONFLICT, STATUS_FORBIDDEN, STATUS_NOT_FOUND, STATUS_UNAUTHORIZED


ROLE_ALIASES = {
    "agency": "admin",
    "agency_admin": "admin",
    "admin": "admin",
    "agent": "agent",
    "owner": "owner",
    "property_owner": "owner",
    "registered_user": "registered_user",
    "user": "registered_user",
    "super_admin": "super_admin",
}


def normalize_role_name(role: str) -> str:
    return ROLE_ALIASES.get(role.strip().lower(), role.strip().lower())


def normalize_username(username: str) -> str:
    return username.strip().lower()


def resolve_effective_sign_in_role(db: Session, *, user: User, requested_role: str) -> str:
    role = normalize_role_name(requested_role)
    if user_has_role(db, user.id, role):
        return role
    if role == "admin" and user_has_role(db, user.id, "super_admin"):
        return "super_admin"
    raise HTTPException(status_code=STATUS_FORBIDDEN, detail="Account role is not allowed for this sign-in")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def generate_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_expired(expires_at: datetime) -> bool:
    current_time = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()
    return expires_at < current_time


def otp_remaining_minutes(expires_at: datetime) -> int:
    current_time = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()
    remaining_seconds = int((expires_at - current_time).total_seconds())
    if remaining_seconds <= 0:
        return 0
    return (remaining_seconds + 59) // 60


def find_user_by_username(db: Session, username: str) -> User | None:
    normalized = normalize_username(username)
    return db.execute(
        select(User).where(
            or_(
                User.email == normalized,
                User.phone_number == username.strip(),
            )
        )
    ).scalar_one_or_none()


def get_or_create_role(db: Session, role_name: str) -> Role:
    normalized = normalize_role_name(role_name)
    role = db.execute(select(Role).where(Role.name == normalized)).scalar_one_or_none()
    if role:
        return role

    role = Role(
        id=uuid4(),
        name=normalized,
        description=f"{normalized.replace('_', ' ').title()} role",
    )
    db.add(role)
    db.flush()
    return role


def user_has_role(db: Session, user_id: UUID, role_name: str) -> bool:
    normalized = normalize_role_name(role_name)
    return bool(
        db.execute(
            select(Role.id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.name == normalized)
        ).first()
    )


def assign_role(db: Session, user_id: UUID, role_name: str, assigned_by: UUID | None = None) -> None:
    role = get_or_create_role(db, role_name)
    already_assigned = db.execute(
        select(
            exists().where(
                UserRole.user_id == user_id,
                UserRole.role_id == role.id,
            )
        )
    ).scalar()
    if already_assigned:
        return

    db.add(
        UserRole(
            user_id=user_id,
            role_id=role.id,
            assigned_by=assigned_by,
        )
    )


def _role_permissions(db: Session, role_id: UUID) -> list[dict]:
    permissions = db.execute(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    ).scalars().all()
    return [
        {
            "id": str(permission.id),
            "code": permission.code,
            "description": permission.description,
            "created_at": _iso(permission.created_at),
        }
        for permission in permissions
    ]


def load_user_roles(db: Session, user_id: UUID) -> list[Role]:
    return db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name)
    ).scalars().all()


def serialize_agency(agency: AgencyMaster | None) -> dict | None:
    if not agency:
        return None
    verification_status = (
        "Verified"
        if agency.is_verified
        else "Rejected" if getattr(agency, "status", "") == "REJECTED" else "Pending Verification"
    )
    return with_readable_media_urls({
        "id": str(agency.id),
        "agency_id": str(agency.id),
        "agency_name": agency.agency_name,
        "agency_trade_name": agency.agency_trade_name,
        "legal_document_s3_link": agency.legal_document_s3_link,
        "email": agency.email,
        "phone": agency.phone,
        "logo_url": agency.logo_url,
        "profile_picture_url": agency.logo_url,
        "website": agency.website,
        "address": agency.address,
        "city": agency.city,
        "state": agency.state,
        "country": agency.country,
        "zip_code": agency.zip_code,
        "is_active": bool(agency.is_active),
        "is_verified": bool(agency.is_verified),
        "status": getattr(agency, "status", "ACTIVE" if agency.is_active else "PENDING_APPROVAL"),
        "agency_status": "Active" if agency.is_active else "Inactive",
        "verification_status": verification_status,
        "currency": agency.currency or "JOD",
        "measurement_unit": agency.measurement_unit or "sqm",
        "created_at": _iso(agency.created_at),
        "updated_at": _iso(agency.updated_at),
    })


def requires_password_set(db: Session, user: User, roles: list[Role] | None = None) -> bool:
    if not user.password_hash:
        return True

    role_names = {normalize_role_name(role.name) for role in (roles or load_user_roles(db, user.id))}
    if "agent" not in role_names:
        return False

    profile = db.get(AgentProfile, user.id)
    return bool(profile and profile.status == "ACTIVE" and profile.password_set_at is None)


def mark_password_set(db: Session, user: User) -> None:
    profile = db.get(AgentProfile, user.id)
    if profile and profile.password_set_at is None:
        profile.password_set_at = utc_now()


def serialize_user(db: Session, user: User) -> dict:
    roles = load_user_roles(db, user.id)
    role_names = tuple(role.name for role in roles)
    primary_agency_id = primary_agency_id_for_context(db, user, role_names)
    agency = db.get(AgencyMaster, primary_agency_id) if primary_agency_id else None
    mapped_agencies = [
        serialize_agency(db.get(AgencyMaster, mapping.agency_id))
        for mapping in active_mappings(db, user_id=user.id)
    ]
    mapped_agencies = [item for item in mapped_agencies if item is not None]
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "is_active": bool(user.is_active),
        "is_email_verified": bool(user.is_email_verified),
        "is_phone_verified": bool(user.is_phone_verified),
        "profile_picture_url": user.profile_picture_url,
        "roles": [
            {
                "id": str(role.id),
                "name": role.name,
                "description": role.description,
                "permissions": _role_permissions(db, role.id),
                "created_at": _iso(role.created_at),
            }
            for role in roles
        ],
        "agency": serialize_agency(agency),
        "agencies": mapped_agencies,
        "has_agency": bool(mapped_agencies or agency),
        "created_at": _iso(user.created_at),
        "requires_password_set": requires_password_set(db, user, roles),
        "status": "active" if user.is_active else "inactive",
    }


def create_auth_tokens(db: Session, user: User, role_name: str | None = None) -> dict:
    # Central gate: never issue JWTs to non-ACTIVE agents (covers login + refresh).
    ensure_agent_can_authenticate(db, user)
    settings = get_settings()
    loaded_roles = load_user_roles(db, user.id)
    roles = [role.name for role in loaded_roles]
    primary_role = normalize_role_name(role_name) if role_name else (roles[0] if roles else None)
    return {
        "access_token": create_token(
            subject=str(user.id),
            token_type="access",
            expires_in_seconds=settings.auth_access_token_seconds,
            role_name=primary_role,
            roles=roles,
        ),
        "refresh_token": create_token(
            subject=str(user.id),
            token_type="refresh",
            expires_in_seconds=settings.auth_refresh_token_seconds,
            role_name=primary_role,
            roles=roles,
        ),
        "id_token": create_token(
            subject=str(user.id),
            token_type="id",
            expires_in_seconds=settings.auth_access_token_seconds,
            role_name=primary_role,
            roles=roles,
        ),
        "token_type": "Bearer",
        "expires_in": settings.auth_access_token_seconds,
        "requires_password_set": requires_password_set(db, user, loaded_roles),
        "remember_me_cookie": False,
    }


def ensure_agent_can_authenticate(db: Session, user: User) -> None:
    """Block agent login/token issuance unless agent profile status is ACTIVE."""
    if not user_has_role(db, user.id, "agent"):
        return

    profile = db.get(AgentProfile, user.id)
    status = ((profile.status if profile else None) or "").strip().upper()
    if status == "ACTIVE":
        return

    if status == "PENDING_REVIEW":
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="Your account is pending admin approval.",
        )
    if status == "DECLINED":
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="Your account has been declined by an administrator.",
        )
    if status == "INACTIVE":
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="Your account is inactive.",
        )
    if status in {"INVITED", "PENDING_PASSWORD", ""}:
        raise HTTPException(
            status_code=STATUS_FORBIDDEN,
            detail="Your account is pending admin approval.",
        )
    raise HTTPException(
        status_code=STATUS_FORBIDDEN,
        detail="Your account is not approved for login.",
    )


def authenticate_password(db: Session, *, username: str, password: str) -> User:
    user = find_user_by_username(db, username)
    if not user or not user.is_active:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid credentials")
    if not user.password_hash or not verify_secret(password, user.password_hash):
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid credentials")
    ensure_agent_can_authenticate(db, user)
    return user


def create_otp_challenge(db: Session, *, user: User, purpose: str, new_value: str) -> tuple[UserProfileChangeChallenge, str]:
    settings = get_settings()
    otp = generate_otp()
    challenge = UserProfileChangeChallenge(
        id=uuid4(),
        user_id=user.id,
        purpose=purpose,
        new_value=new_value,
        otp_hash=hash_secret(otp),
        expires_at=utc_now() + timedelta(seconds=settings.auth_otp_ttl_seconds),
    )
    db.add(challenge)
    db.flush()
    return challenge, otp


def verify_otp_challenge(
    db: Session,
    *,
    purpose: str,
    code: str,
    user: User | None = None,
    challenge_id: UUID | None = None,
    new_value: str | None = None,
) -> UserProfileChangeChallenge:
    stmt = select(UserProfileChangeChallenge).where(UserProfileChangeChallenge.purpose == purpose)
    if challenge_id:
        stmt = stmt.where(UserProfileChangeChallenge.id == challenge_id)
    if user:
        stmt = stmt.where(UserProfileChangeChallenge.user_id == user.id)
    if new_value:
        stmt = stmt.where(UserProfileChangeChallenge.new_value == new_value)

    challenge = db.execute(stmt.order_by(UserProfileChangeChallenge.created_at.desc())).scalars().first()
    if not challenge:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Verification code not found")
    if is_expired(challenge.expires_at):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Verification code has expired")
    if not verify_secret(code, challenge.otp_hash):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid verification code")
    return challenge


def create_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone_number: str | None,
    password: str | None,
    role: str,
    agency_id: UUID | None = None,
) -> User:
    normalized_email = normalize_username(email)
    existing = db.execute(select(User.id).where(User.email == normalized_email)).first()
    if existing:
        raise HTTPException(status_code=STATUS_CONFLICT, detail="User already exists")

    user = User(
        id=uuid4(),
        full_name=full_name,
        email=normalized_email,
        phone_number=phone_number,
        password_hash=hash_secret(password) if password else None,
        is_active=True,
        is_email_verified=False,
        is_phone_verified=False,
        preferred_language=get_settings().default_locale,
        agency_id=agency_id,
    )
    db.add(user)
    db.flush()
    assign_role(db, user.id, role)
    normalized_role = normalize_role_name(role)
    relationship_type = {
        "admin": REL_AGENCY_ADMIN,
        "agent": REL_AGENT,
        "owner": REL_PROPERTY_OWNER,
        "registered_user": REL_PROPERTY_OWNER,
    }.get(normalized_role)
    if agency_id and relationship_type:
        ensure_user_agency_mapping(
            db,
            user_id=user.id,
            agency_id=agency_id,
            relationship_type=relationship_type,
            is_primary=True,
        )
    return user


def build_otp_response_data(
    *,
    otp: str | None = None,
    dev_email_otp: str | None = None,
    dev_phone_otp: str | None = None,
    **extra: object,
) -> dict[str, object]:
    settings = get_settings()
    data: dict[str, object] = dict(extra)
    if settings.expose_otp_in_response:
        if otp is not None:
            data["otp"] = otp
        if dev_email_otp is not None:
            data["dev_email_otp"] = dev_email_otp
        if dev_phone_otp is not None:
            data["dev_phone_otp"] = dev_phone_otp
    return data


def build_otp_response_meta(*, otp: str | None = None) -> dict[str, object]:
    settings = get_settings()
    if settings.expose_otp_in_response and otp is not None:
        return {"otp": otp}
    return {}


def otp_delivery_message(*, fallback_dev_message: str, sent_message: str) -> str:
    settings = get_settings()
    if settings.expose_otp_in_response:
        return fallback_dev_message
    return sent_message


def send_dev_otp(
    *,
    user: User,
    purpose: str,
    otp: str,
    challenge: UserProfileChangeChallenge | None = None,
) -> None:
    settings = get_settings()
    if challenge is not None:
        expiry_minutes = otp_remaining_minutes(challenge.expires_at)
    else:
        expiry_minutes = max(settings.auth_otp_ttl_seconds // 60, 1)
    if user.email:
        subject, text_body, html_body = build_otp_verification_email(
            app_name=settings.app_name,
            otp=otp,
            expiry_minutes=expiry_minutes,
            subject=settings.email_otp_verification_subject,
        )
        send_email_notification(
            to_email=user.email,
            subject=subject,
            body=text_body,
            html_body=html_body,
        )
    if user.phone_number:
        send_sms_notification(
            to_phone=user.phone_number,
            body=f"Your {settings.app_name} verification code is {otp}",
        )


def verify_refresh_token(db: Session, token: str, username: str) -> User:
    payload = verify_token(token, expected_type="refresh")
    if not payload:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, UUID(str(payload.get("sub"))))
    if not user or normalize_username(user.email) != normalize_username(username):
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid refresh token")
    ensure_agent_can_authenticate(db, user)
    return user


def get_user_or_404(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="User not found")
    return user
