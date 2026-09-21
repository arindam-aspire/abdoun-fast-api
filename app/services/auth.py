from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import ClientError
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
from app.services.notifications import send_sms_notification
from app.services.notifications.email.service import get_email_service
from app.services.user_agencies import (
    REL_AGENCY_ADMIN,
    REL_AGENT,
    REL_PROPERTY_OWNER,
    active_mappings,
    ensure_user_agency_mapping,
    primary_agency_id_for_context,
)
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_CONFLICT, STATUS_FORBIDDEN, STATUS_NOT_FOUND, STATUS_UNAUTHORIZED

logger = logging.getLogger(__name__)
_E164_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


def _normalize_cognito_phone(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    compact = re.sub(r"[\s\-()]", "", phone_number.strip())
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    elif compact.startswith("0") and compact[1:].isdigit():
        compact = f"+962{compact[1:]}"
    elif compact.isdigit() and compact.startswith("962"):
        compact = f"+{compact}"
    elif compact.isdigit() and 8 <= len(compact) <= 15:
        compact = f"+{compact}"
    if _E164_PHONE.match(compact):
        return compact
    return None


class CognitoUsernameExists(Exception):
    """Raised when Cognito already has the signup username."""


class CognitoService:
    def __init__(self) -> None:
        settings = get_settings()
        self.region = settings.cognito_region
        self.user_pool_id = settings.cognito_user_pool_id
        self.client_id = settings.cognito_app_client_id
        self.client_secret = settings.cognito_app_client_secret
        self._client: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.user_pool_id and self.client_id)

    def client(self):
        if self._client is None:
            self._client = boto3.client("cognito-idp", region_name=self.region)
        return self._client

    def secret_hash(self, username: str) -> str | None:
        if not self.client_secret:
            return None
        digest = hmac.new(
            self.client_secret.encode("utf-8"),
            f"{username}{self.client_id}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _auth_parameters(self, username: str, password: str) -> dict[str, str]:
        params = {"USERNAME": username, "PASSWORD": password}
        hashed = self.secret_hash(username)
        if hashed:
            params["SECRET_HASH"] = hashed
        return params

    def _with_secret(self, username: str, payload: dict[str, Any]) -> dict[str, Any]:
        hashed = self.secret_hash(username)
        if hashed:
            payload["SecretHash"] = hashed
        return payload

    def signup(self, *, email: str, password: str, full_name: str, phone_number: str | None) -> str:
        username = email.strip().lower()
        name = (full_name or "").strip()
        phone = _normalize_cognito_phone(phone_number)
        attribute_sets: list[list[dict[str, str]]] = []
        email_attrs = [{"Name": "email", "Value": username}]
        named_attrs = [*email_attrs]
        if name:
            named_attrs.append({"Name": "name", "Value": name})
        if phone:
            attribute_sets.append([*named_attrs, {"Name": "phone_number", "Value": phone}])
        attribute_sets.append(named_attrs)
        if name:
            without_name = [*email_attrs]
            if phone:
                attribute_sets.append([*without_name, {"Name": "phone_number", "Value": phone}])
            attribute_sets.append(without_name)

        last_error: ClientError | None = None
        for attributes in attribute_sets:
            payload: dict[str, Any] = {
                "ClientId": self.client_id,
                "Username": username,
                "Password": password,
                "UserAttributes": attributes,
            }
            self._with_secret(username, payload)
            try:
                response = self.client().sign_up(**payload)
                return str(response.get("UserSub") or "")
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code == "UsernameExistsException":
                    raise CognitoUsernameExists from exc
                if code == "InvalidParameterException":
                    last_error = exc
                    logger.warning(
                        "cognito_signup_invalid_parameter attrs=%s message=%s",
                        ",".join(item["Name"] for item in attributes),
                        exc.response.get("Error", {}).get("Message", ""),
                    )
                    continue
                self._raise(exc, "Unable to register account")
        if last_error is not None:
            self._raise(last_error, "Unable to register account")
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Unable to register account")

    def confirm_signup(self, *, email: str, code: str) -> None:
        username = email.strip().lower()
        payload: dict[str, Any] = {
            "ClientId": self.client_id,
            "Username": username,
            "ConfirmationCode": code.strip(),
        }
        self._with_secret(username, payload)
        try:
            self.client().confirm_sign_up(**payload)
        except ClientError as exc:
            self._raise(exc, "Unable to confirm account")

    def resend_confirmation_code(self, *, email: str) -> None:
        username = email.strip().lower()
        payload: dict[str, Any] = {"ClientId": self.client_id, "Username": username}
        self._with_secret(username, payload)
        try:
            self.client().resend_confirmation_code(**payload)
        except ClientError as exc:
            self._raise(exc, "Unable to resend confirmation code")

    def get_user_status(self, *, email: str) -> str | None:
        username = email.strip().lower()
        try:
            response = self.client().admin_get_user(UserPoolId=self.user_pool_id, Username=username)
        except ClientError:
            return None
        return str(response.get("UserStatus") or "") or None

    def login_password(self, *, email: str, password: str) -> dict[str, Any]:
        username = email.strip().lower()
        auth_parameters = self._auth_parameters(username, password)
        try:
            return self.client().initiate_auth(
                ClientId=self.client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters=auth_parameters,
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            message = error.get("Message", "")
            flow_disabled = code == "InvalidParameterException" and "USER_PASSWORD_AUTH" in message
            secret_failed = code == "NotAuthorizedException" and "secret hash" in message.lower()
            if flow_disabled or secret_failed:
                logger.warning("cognito_user_password_auth_unavailable code=%s; using ADMIN_USER_PASSWORD_AUTH", code)
                return self._admin_login(username, password)
            self._raise(exc, "Invalid credentials")
            raise

    def _admin_login(self, username: str, password: str) -> dict[str, Any]:
        try:
            return self.client().admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters=self._auth_parameters(username, password),
            )
        except ClientError as exc:
            self._raise(exc, "Invalid credentials")
            raise

    def get_user_sub(self, *, email: str) -> str:
        username = email.strip().lower()
        try:
            response = self.client().admin_get_user(UserPoolId=self.user_pool_id, Username=username)
        except ClientError:
            response = None
        if response:
            for attr in response.get("UserAttributes") or []:
                if attr.get("Name") == "sub" and attr.get("Value"):
                    return str(attr["Value"])
        try:
            listed = self.client().list_users(
                UserPoolId=self.user_pool_id,
                Filter=f'email = "{username}"',
                Limit=1,
            )
        except ClientError as exc:
            self._raise(exc, "Unable to load Cognito user")
            raise
        users = listed.get("Users") or []
        if users:
            for attr in users[0].get("Attributes") or []:
                if attr.get("Name") == "sub" and attr.get("Value"):
                    return str(attr["Value"])
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Cognito user id was not returned")

    def forgot_password(self, *, email: str) -> None:
        username = email.strip().lower()
        payload: dict[str, Any] = {"ClientId": self.client_id, "Username": username}
        self._with_secret(username, payload)
        try:
            self.client().forgot_password(**payload)
        except ClientError as exc:
            self._raise(exc, "Unable to start password reset")

    def confirm_forgot_password(self, *, email: str, code: str, new_password: str) -> None:
        username = email.strip().lower()
        payload: dict[str, Any] = {
            "ClientId": self.client_id,
            "Username": username,
            "ConfirmationCode": code.strip(),
            "Password": new_password,
        }
        self._with_secret(username, payload)
        try:
            self.client().confirm_forgot_password(**payload)
        except ClientError as exc:
            self._raise(exc, "Unable to reset password")

    def admin_confirm_signup(self, *, email: str) -> None:
        username = email.strip().lower()
        try:
            self.client().admin_confirm_sign_up(
                UserPoolId=self.user_pool_id,
                Username=username,
            )
        except ClientError as exc:
            message = (exc.response.get("Error", {}).get("Message") or "").lower()
            if "already" in message and "confirm" in message:
                return
            self._raise(exc, "Unable to confirm account")

    def admin_set_password(self, *, email: str, password: str) -> None:
        try:
            self.client().admin_set_user_password(
                UserPoolId=self.user_pool_id,
                Username=email.strip().lower(),
                Password=password,
                Permanent=True,
            )
        except ClientError as exc:
            self._raise(exc, "Unable to change password")

    def sub_from_auth_result(self, auth_result: dict[str, Any]) -> str:
        id_token = ((auth_result or {}).get("AuthenticationResult") or {}).get("IdToken") or ""
        if not id_token:
            return ""
        try:
            payload_segment = id_token.split(".")[1]
            padded = payload_segment + "=" * ((4 - len(payload_segment) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        except (IndexError, ValueError, json.JSONDecodeError):
            return ""
        return str(payload.get("sub") or "")

    def _raise(self, exc: ClientError, fallback: str) -> None:
        error = exc.response.get("Error", {})
        code = error.get("Code", "")
        message = error.get("Message", "") or fallback
        logger.warning("cognito_error code=%s message=%s", code, message)
        mapped = {
            "UsernameExistsException": (STATUS_CONFLICT, "An account with this email already exists. Please sign in."),
            "AliasExistsException": (STATUS_CONFLICT, "An account with this phone number already exists. Please sign in."),
            "UserNotFoundException": (STATUS_UNAUTHORIZED, "Invalid credentials"),
            "NotAuthorizedException": (STATUS_UNAUTHORIZED, "Invalid credentials"),
            "UserNotConfirmedException": (STATUS_BAD_REQUEST, "Account is not confirmed"),
            "CodeMismatchException": (STATUS_BAD_REQUEST, "Invalid verification code"),
            "ExpiredCodeException": (STATUS_BAD_REQUEST, "Verification code has expired"),
            "LimitExceededException": (STATUS_BAD_REQUEST, "Too many attempts. Try again later"),
            "InvalidPasswordException": (STATUS_BAD_REQUEST, "Password does not meet requirements"),
            "InvalidParameterException": (STATUS_BAD_REQUEST, message or fallback),
        }
        status, detail = mapped.get(code, (STATUS_BAD_REQUEST, fallback))
        if "secret hash" in message.lower():
            detail = "Authentication configuration error"
        raise HTTPException(status_code=status, detail=detail) from exc


cognito_service = CognitoService()


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
        "currency": agency.currency or get_settings().default_currency,
        "measurement_unit": agency.measurement_unit or get_settings().default_measurement_unit,
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
    if not user:
        raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid credentials")

    if cognito_service.enabled:
        try:
            auth_result = cognito_service.login_password(email=user.email, password=password)
            sub = cognito_service.sub_from_auth_result(auth_result) or cognito_service.get_user_sub(email=user.email)
            if sub:
                user.cognito_sub = sub
            user.password_hash = hash_secret(password)
            user.is_email_verified = True
            consumer_roles = {normalize_role_name(role.name) for role in load_user_roles(db, user.id)}
            if consumer_roles & {"registered_user", "owner"}:
                user.is_active = True
            elif not user.is_active:
                raise HTTPException(status_code=STATUS_UNAUTHORIZED, detail="Invalid credentials")
            ensure_agent_can_authenticate(db, user)
            db.flush()
            return user
        except HTTPException as exc:
            if exc.status_code == STATUS_BAD_REQUEST:
                raise
            if user.cognito_sub:
                raise

    if not user.is_active:
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


def _temporary_cognito_password() -> str:
    return f"Ag!{secrets.token_urlsafe(18)}aA1"


def register_cognito_user(
    *,
    email: str,
    full_name: str,
    phone_number: str | None,
    password: str | None = None,
    on_existing: str = "reuse",
    resolve_sub: bool = True,
) -> str:
    """Register the user in Cognito using the same signup flow as `/auth/signup`.

    `on_existing=conflict_if_confirmed` matches self-service signup: confirmed
    Cognito users are rejected, unconfirmed users get a resent code.
    `on_existing=reuse` does not create a duplicate; it returns the existing sub.
    """
    if not cognito_service.enabled:
        return ""

    try:
        sub = cognito_service.signup(
            email=email,
            password=password or _temporary_cognito_password(),
            full_name=full_name,
            phone_number=phone_number,
        )
    except CognitoUsernameExists:
        status = cognito_service.get_user_status(email=email)
        confirmed_statuses = {"CONFIRMED", "RESET_REQUIRED", "FORCE_CHANGE_PASSWORD"}
        if on_existing == "conflict_if_confirmed" and status in confirmed_statuses:
            raise HTTPException(
                status_code=STATUS_CONFLICT,
                detail="An account with this email already exists. Please sign in.",
            )
        if on_existing == "conflict_if_confirmed" and status not in confirmed_statuses:
            cognito_service.resend_confirmation_code(email=email)
            return ""
        sub = ""

    if not resolve_sub:
        return str(sub or "")
    if sub:
        return str(sub)
    return cognito_service.get_user_sub(email=email)


def create_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone_number: str | None,
    password: str | None,
    role: str,
    agency_id: UUID | None = None,
    is_active: bool = True,
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
        is_active=is_active,
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


def register_signup_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone_number: str | None,
    password: str,
    role: str,
) -> User:
    existing = find_user_by_username(db, email)
    if existing and (existing.is_email_verified or existing.cognito_sub):
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )

    register_cognito_user(
        email=email,
        full_name=full_name,
        phone_number=phone_number,
        password=password,
        on_existing="conflict_if_confirmed",
        resolve_sub=False,
    )

    if existing:
        existing.full_name = full_name
        existing.phone_number = phone_number or existing.phone_number
        existing.password_hash = hash_secret(password)
        existing.is_active = False
        existing.is_email_verified = False
        assign_role(db, existing.id, role)
        db.flush()
        return existing

    return create_user(
        db,
        full_name=full_name,
        email=email,
        phone_number=phone_number,
        password=password,
        role=role,
        is_active=False,
    )


def _activate_confirmed_signup(user: User) -> None:
    if cognito_service.enabled:
        cognito_service.admin_confirm_signup(email=user.email)
        sub = cognito_service.get_user_sub(email=user.email)
        if not sub:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Cognito user id was not returned")
        user.cognito_sub = sub
    user.is_email_verified = True
    user.is_active = True


def confirm_signup_user(db: Session, *, email: str, code: str) -> User:
    user = find_user_by_username(db, email)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Account not found")

    if cognito_service.enabled:
        try:
            cognito_service.confirm_signup(email=user.email, code=code)
        except HTTPException as exc:
            if exc.status_code != STATUS_BAD_REQUEST:
                raise
            try:
                verify_otp_challenge(
                    db,
                    purpose="signup_confirm",
                    code=code,
                    user=user,
                    new_value=normalize_username(user.email),
                )
            except HTTPException:
                raise exc from None
    else:
        verify_otp_challenge(
            db,
            purpose="signup_confirm",
            code=code,
            user=user,
            new_value=normalize_username(user.email),
        )

    _activate_confirmed_signup(user)
    db.flush()
    return user


def resend_signup_confirmation(db: Session, *, email: str) -> str | None:
    user = find_user_by_username(db, email)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Account not found")
    if user.is_email_verified and user.is_active:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Account is already verified")

    if cognito_service.enabled:
        try:
            status = cognito_service.get_user_status(email=user.email)
            if status not in {"CONFIRMED", "RESET_REQUIRED", "FORCE_CHANGE_PASSWORD"}:
                cognito_service.resend_confirmation_code(email=user.email)
        except HTTPException as exc:
            if exc.status_code not in {STATUS_UNAUTHORIZED, STATUS_BAD_REQUEST}:
                raise

    challenge, otp = create_otp_challenge(
        db,
        user=user,
        purpose="signup_confirm",
        new_value=normalize_username(user.email),
    )
    send_dev_otp(user=user, purpose="signup", otp=otp, challenge=challenge)
    return otp


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
    identifier: str | None = None,
) -> None:
    settings = get_settings()
    if challenge is not None:
        expiry_minutes = otp_remaining_minutes(challenge.expires_at)
    else:
        expiry_minutes = max(settings.auth_otp_ttl_seconds // 60, 1)

    requested = (identifier or "").strip()
    requested_is_email = "@" in requested
    deliver_email = bool(user.email) and (not requested or requested_is_email)
    deliver_sms = bool(user.phone_number) and (not requested or not requested_is_email)

    if deliver_email:
        email_service = get_email_service()
        if "password" in purpose.lower():
            email_service.send_password_reset(
                to_email=user.email,
                subject=settings.email_otp_verification_subject,
                text_body="",
                otp=otp,
                expiry_minutes=expiry_minutes,
                app_name=settings.app_name,
            )
        else:
            email_service.send_otp_verification(
                to_email=user.email,
                otp=otp,
                expiry_minutes=expiry_minutes,
                subject=settings.email_otp_verification_subject,
                app_name=settings.app_name,
            )
    if deliver_sms:
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
