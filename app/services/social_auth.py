"""Social sign-in and sign-up for User and Owner accounts.

Google and Facebook authenticate only through a Cognito ID token. The backend
does not call Google or Facebook. Apple may still present a Cognito ID token
or an Apple identity token. Provider identity is the (`provider`,
`provider_user_id`) pair stored in `social_accounts`, and the Cognito subject
is stored on `users.cognito_sub`. Email is never used as that identity. A
provider email that already belongs to an MLS account is not linked or merged.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import uuid4

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.live_schema import SocialAccount, User
from app.services.auth import (
    create_user,
    find_user_by_username,
    load_user_roles,
    normalize_role_name,
    normalize_username,
    utc_now,
)
from app.utils.status_codes import (
    STATUS_BAD_REQUEST,
    STATUS_CONFLICT,
    STATUS_FORBIDDEN,
    STATUS_SERVICE_UNAVAILABLE,
    STATUS_UNAUTHORIZED,
)

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = frozenset({"google", "facebook", "apple"})
SOCIAL_ROLES = frozenset({"registered_user", "owner"})
BLOCKED_SOCIAL_ROLES = frozenset({"agent", "admin", "super_admin"})
_MAX_TOKEN_LENGTH = 10000
_jwks_clients: dict[str, PyJWKClient] = {}


@dataclass(frozen=True)
class SocialIdentity:
    provider: str
    provider_user_id: str
    email: str | None
    email_verified: bool
    full_name: str
    cognito_sub: str | None = None


class _SocialTokenError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _social_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _csv_values(raw_value: str | None) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


def _normalize_provider(provider: str | None) -> str:
    normalized = (provider or "").strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise _social_error(
            STATUS_BAD_REQUEST,
            "SOCIAL_PROVIDER_UNSUPPORTED",
            "Social sign-in provider is not supported.",
        )
    return normalized


def _signing_key_for_token(jwks_url: str, token: str):
    client = _jwks_clients.get(jwks_url)
    if client is None:
        settings = get_settings()
        client = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=max(settings.social_jwks_cache_seconds, 0),
            timeout=max(settings.social_provider_http_timeout_seconds, 1),
        )
        _jwks_clients[jwks_url] = client
    return client.get_signing_key_from_jwt(token)


def _claim_verified(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _display_name(claims: dict[str, Any], email: str | None) -> str:
    name = str(claims.get("name") or "").strip()
    if not name:
        given = str(claims.get("given_name") or "").strip()
        family = str(claims.get("family_name") or "").strip()
        name = f"{given} {family}".strip()
    if not name and email:
        name = email.split("@", 1)[0].strip()
    return (name or "User")[:255]


def _email_from_claims(claims: dict[str, Any]) -> tuple[str | None, bool]:
    raw_email = str(claims.get("email") or "").strip()
    if not raw_email or "@" not in raw_email:
        return None, False
    return normalize_username(raw_email), _claim_verified(claims.get("email_verified"))


def _decode_oidc_token(
    *,
    token: str,
    jwks_url: str,
    audiences: list[str],
    issuers: list[str],
) -> dict[str, Any]:
    if not jwks_url or not audiences or not issuers:
        raise _SocialTokenError("not_configured")
    if token.count(".") != 2:
        raise _SocialTokenError("invalid")
    settings = get_settings()
    try:
        signing_key = _signing_key_for_token(jwks_url, token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audiences,
            options={"require": ["exp", "sub", "iss", "aud"]},
            leeway=max(settings.social_token_leeway_seconds, 0),
        )
    except jwt.ExpiredSignatureError:
        raise _SocialTokenError("expired") from None
    except jwt.InvalidAudienceError:
        raise _SocialTokenError("invalid_audience") from None
    except jwt.InvalidIssuerError:
        raise _SocialTokenError("invalid_issuer") from None
    except PyJWKClientConnectionError as exc:
        logger.warning("social_jwks_unavailable error_type=%s", type(exc).__name__)
        raise _SocialTokenError("unavailable") from None
    except jwt.PyJWTError:
        raise _SocialTokenError("invalid") from None
    accepted_issuers = {item.strip().rstrip("/") for item in issuers}
    issuer = str(payload.get("iss") or "").strip().rstrip("/") if isinstance(payload, dict) else ""
    if not isinstance(payload, dict) or issuer not in accepted_issuers:
        raise _SocialTokenError("invalid_issuer")
    return payload


def _identity_from_oidc_claims(provider: str, claims: dict[str, Any]) -> SocialIdentity:
    subject = str(claims.get("sub") or "").strip()
    if not subject or len(subject) > 255:
        raise _SocialTokenError("invalid")
    email, email_verified = _email_from_claims(claims)
    return SocialIdentity(
        provider=provider,
        provider_user_id=subject,
        email=email,
        email_verified=email_verified,
        full_name=_display_name(claims, email),
    )


def _apple_oidc_settings() -> tuple[str, list[str], list[str]]:
    settings = get_settings()
    return (
        settings.apple_oauth_jwks_url,
        _csv_values(settings.apple_oauth_client_ids),
        _csv_values(settings.apple_oauth_issuers),
    )


def _raise_token_error(error: _SocialTokenError) -> NoReturn:
    if error.reason == "expired":
        raise _social_error(
            STATUS_UNAUTHORIZED,
            "SOCIAL_TOKEN_EXPIRED",
            "Social sign-in token has expired.",
        ) from None
    if error.reason == "not_configured":
        raise _social_error(
            STATUS_SERVICE_UNAVAILABLE,
            "SOCIAL_PROVIDER_NOT_CONFIGURED",
            "Social sign-in is not configured for this provider.",
        ) from None
    if error.reason == "unavailable":
        raise _social_error(
            STATUS_SERVICE_UNAVAILABLE,
            "SOCIAL_PROVIDER_UNAVAILABLE",
            "Social sign-in provider could not be reached.",
        ) from None
    if error.reason == "cognito_required":
        raise _social_error(
            STATUS_UNAUTHORIZED,
            "SOCIAL_COGNITO_TOKEN_REQUIRED",
            "Google and Facebook sign-in require a Cognito identity token.",
        ) from None
    messages = {
        "invalid_audience": "Social sign-in token audience is not accepted.",
        "invalid_issuer": "Social sign-in token issuer is not accepted.",
        "provider_mismatch": "Social sign-in token does not match the requested provider.",
        "not_id_token": "A Cognito identity token is required.",
    }
    raise _social_error(
        STATUS_UNAUTHORIZED,
        "SOCIAL_TOKEN_INVALID",
        messages.get(error.reason, "Social sign-in token is invalid."),
    ) from None


def _unverified_claims(token: str) -> dict[str, Any] | None:
    """Read claims only to choose a verifier. Signature checks happen later."""
    if token.count(".") != 2:
        return None
    try:
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
                "verify_iss": False,
            },
        )
    except jwt.PyJWTError:
        return None
    return payload if isinstance(payload, dict) else None


def _looks_like_cognito_issuer(issuer: str) -> bool:
    normalized = issuer.strip().rstrip("/")
    return normalized.startswith("https://cognito-idp.") and ".amazonaws.com/" in normalized


def _cognito_token_route(token: str) -> str:
    """Return cognito, reject, or provider. The token is not trusted yet."""
    claims = _unverified_claims(token)
    if not claims:
        return "provider"
    issuer = str(claims.get("iss") or "").strip().rstrip("/")
    if not issuer:
        return "provider"
    expected = get_settings().resolved_cognito_issuer()
    if expected and issuer == expected:
        return "cognito"
    if _looks_like_cognito_issuer(issuer):
        return "reject"
    return "provider"


def _cognito_provider_aliases() -> dict[str, str]:
    settings = get_settings()
    aliases: dict[str, str] = {}
    for provider, raw_names in (
        ("google", settings.cognito_google_provider_names),
        ("facebook", settings.cognito_facebook_provider_names),
        ("apple", settings.cognito_apple_provider_names),
    ):
        for name in _csv_values(raw_names):
            aliases[name.casefold()] = provider
    return aliases


def _identity_records(claims: dict[str, Any]) -> list[dict[str, Any]]:
    raw = claims.get("identities")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise _SocialTokenError("invalid") from exc
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if not isinstance(raw, list):
        raise _SocialTokenError("invalid")
    return [item for item in raw if isinstance(item, dict)]


def _username_subject(username: str, alias: str) -> str | None:
    prefix = f"{alias}_"
    if not username.casefold().startswith(prefix.casefold()):
        return None
    subject = username[len(prefix) :].strip()
    return subject or None


def _federated_subject(claims: dict[str, Any], requested: str) -> str:
    """Provider user id from the verified Cognito token, never from the request body."""
    aliases = _cognito_provider_aliases()
    records = _identity_records(claims)
    if records:
        for record in records:
            names = (
                str(record.get("providerName") or "").strip(),
                str(record.get("providerType") or "").strip(),
            )
            if not any(aliases.get(name.casefold()) == requested for name in names if name):
                continue
            subject = str(record.get("userId") or "").strip()
            if not subject or len(subject) > 255:
                raise _SocialTokenError("invalid")
            return subject
        raise _SocialTokenError("provider_mismatch")

    username = str(claims.get("cognito:username") or "").strip()
    if not username:
        raise _SocialTokenError("invalid")
    for alias, provider in aliases.items():
        subject = _username_subject(username, alias)
        if subject is None:
            continue
        if provider != requested or len(subject) > 255:
            raise _SocialTokenError("provider_mismatch" if provider != requested else "invalid")
        return subject
    raise _SocialTokenError("provider_mismatch")


def _identity_from_cognito_token(provider: str, token: str) -> SocialIdentity:
    settings = get_settings()
    issuer = settings.resolved_cognito_issuer()
    jwks_url = settings.resolved_cognito_jwks_url()
    client_id = (settings.cognito_app_client_id or "").strip()
    if not issuer or not jwks_url or not client_id:
        raise _SocialTokenError("not_configured")
    claims = _decode_oidc_token(
        token=token,
        jwks_url=jwks_url,
        audiences=[client_id],
        issuers=[issuer],
    )
    if str(claims.get("token_use") or "") != "id":
        raise _SocialTokenError("not_id_token")
    cognito_sub = str(claims.get("sub") or "").strip()
    if not cognito_sub or len(cognito_sub) > 100:
        raise _SocialTokenError("invalid")
    email, email_verified = _email_from_claims(claims)
    if provider == "facebook" and email and not email_verified:
        # Facebook does not send email_verified. Cognito maps the email from the
        # IdP and leaves the claim false. The address still comes from the
        # signed token and is never attached to a different MLS account.
        email_verified = True
    return SocialIdentity(
        provider=provider,
        provider_user_id=_federated_subject(claims, provider),
        email=email,
        email_verified=email_verified,
        full_name=_display_name(claims, email),
        cognito_sub=cognito_sub,
    )


def _cognito_identity_or_none(provider: str, token: str) -> SocialIdentity | None:
    route = _cognito_token_route(token)
    if route == "provider":
        return None
    if route == "reject":
        if not get_settings().resolved_cognito_issuer():
            raise _SocialTokenError("not_configured")
        raise _SocialTokenError("invalid_issuer")
    return _identity_from_cognito_token(provider, token)


def _require_cognito_identity(provider: str, token: str) -> SocialIdentity:
    """Google and Facebook are accepted only as Cognito-issued ID tokens."""
    identity = _cognito_identity_or_none(provider, token)
    if identity is None:
        raise _SocialTokenError("cognito_required")
    return identity


def verify_social_identity(
    *,
    provider: str,
    id_token: str | None = None,
    access_token: str | None = None,
) -> SocialIdentity:
    """Validate a Cognito or Apple assertion and return only verified claims."""
    normalized = _normalize_provider(provider)
    token = (id_token or "").strip()
    opaque_token = (access_token or "").strip()
    if token and len(token) > _MAX_TOKEN_LENGTH:
        _raise_token_error(_SocialTokenError("invalid"))
    if opaque_token and len(opaque_token) > _MAX_TOKEN_LENGTH:
        _raise_token_error(_SocialTokenError("invalid"))
    assertion = token or opaque_token
    if not assertion:
        raise _social_error(
            STATUS_BAD_REQUEST,
            "SOCIAL_TOKEN_MISSING",
            "A provider identity token is required.",
        )

    try:
        if normalized in {"google", "facebook"}:
            return _require_cognito_identity(normalized, assertion)
        cognito_identity = _cognito_identity_or_none(normalized, assertion)
        if cognito_identity is not None:
            return cognito_identity
        if not token:
            raise _social_error(
                STATUS_BAD_REQUEST,
                "SOCIAL_TOKEN_MISSING",
                "A provider identity token is required.",
            )
        jwks_url, audiences, issuers = _apple_oidc_settings()
        claims = _decode_oidc_token(token=token, jwks_url=jwks_url, audiences=audiences, issuers=issuers)
        return _identity_from_oidc_claims(normalized, claims)
    except _SocialTokenError as exc:
        logger.warning("social_token_rejected provider=%s reason=%s", normalized, exc.reason)
        _raise_token_error(exc)


def _requested_social_role(role: str | None, *, required: bool) -> str | None:
    cleaned = (role or "").strip()
    if not cleaned:
        if required:
            raise _social_error(
                STATUS_BAD_REQUEST,
                "SOCIAL_ROLE_REQUIRED",
                "Choose a User or Owner account to continue.",
            )
        return None
    normalized = normalize_role_name(cleaned)
    if normalized not in SOCIAL_ROLES or normalized in BLOCKED_SOCIAL_ROLES:
        raise _social_error(
            STATUS_FORBIDDEN,
            "SOCIAL_ROLE_NOT_ALLOWED",
            "Social sign-in only supports User and Owner accounts.",
        )
    return normalized


def _find_social_account(db: Session, provider: str, provider_user_id: str) -> SocialAccount | None:
    return db.execute(
        select(SocialAccount).where(
            SocialAccount.provider == provider,
            SocialAccount.provider_user_id == provider_user_id,
        )
    ).scalar_one_or_none()


def _authorize_existing_social_user(db: Session, user: User, requested_role: str | None) -> str | None:
    if getattr(user, "deleted_at", None) is not None or user.is_active is not True:
        raise _social_error(STATUS_UNAUTHORIZED, "SOCIAL_ACCOUNT_UNAVAILABLE", "Invalid account")
    role_names = {normalize_role_name(role.name) for role in load_user_roles(db, user.id)}
    if role_names & BLOCKED_SOCIAL_ROLES or not (role_names & SOCIAL_ROLES):
        raise _social_error(
            STATUS_FORBIDDEN,
            "SOCIAL_ROLE_NOT_ALLOWED",
            "Social sign-in is not available for this account.",
        )
    selected = _requested_social_role(requested_role, required=False)
    if selected and selected not in role_names:
        # The client role is not authorization. Keep the role already stored.
        stored = role_names & SOCIAL_ROLES
        if stored == {"owner"}:
            return "owner"
        return "registered_user"
    return selected


def _email_already_registered() -> HTTPException:
    return _social_error(
        STATUS_CONFLICT,
        "SOCIAL_EMAIL_ALREADY_REGISTERED",
        "An account with this email already exists. Sign in with your existing email and password or verification code.",
    )


def _reject_incomplete_profile(identity: SocialIdentity) -> str:
    if not identity.email:
        raise _social_error(
            STATUS_BAD_REQUEST,
            "SOCIAL_PROFILE_INCOMPLETE",
            "The social provider did not return the verified profile details required to create an account.",
        )
    if not identity.email_verified:
        raise _social_error(
            STATUS_BAD_REQUEST,
            "SOCIAL_EMAIL_NOT_VERIFIED",
            "The social provider did not verify this email address.",
        )
    return identity.email


def _load_linked_user(db: Session, account: SocialAccount, requested_role: str | None) -> tuple[User, str | None]:
    user = db.get(User, account.user_id)
    if user is None:
        raise _social_error(STATUS_UNAUTHORIZED, "SOCIAL_ACCOUNT_UNAVAILABLE", "Invalid account")
    return user, _authorize_existing_social_user(db, user, requested_role)


def _find_user_by_cognito_sub(db: Session, cognito_sub: str) -> User | None:
    subject = cognito_sub.strip()
    if not subject:
        return None
    return db.execute(select(User).where(User.cognito_sub == subject)).scalar_one_or_none()


def _bind_cognito_sub(user: User, identity: SocialIdentity) -> None:
    subject = (identity.cognito_sub or "").strip()
    if not subject:
        return
    current = str(getattr(user, "cognito_sub", None) or "").strip()
    if current and current != subject:
        raise _social_error(
            STATUS_CONFLICT,
            "SOCIAL_IDENTITY_CONFLICT",
            "This social account is already registered.",
        )
    if not current:
        user.cognito_sub = subject


def _new_social_account(user: User, identity: SocialIdentity) -> SocialAccount:
    return SocialAccount(
        id=uuid4(),
        user_id=user.id,
        provider=identity.provider,
        provider_user_id=identity.provider_user_id,
    )


def _link_cognito_user(
    db: Session,
    user: User,
    identity: SocialIdentity,
    requested_role: str | None,
) -> tuple[User, str | None]:
    """Attach a Cognito social identity to an application user that already exists."""
    role_name = _authorize_existing_social_user(db, user, requested_role)
    _bind_cognito_sub(user, identity)
    try:
        account = _new_social_account(user, identity)
        db.add(account)
        db.flush()
    except IntegrityError:
        logger.warning("social_identity_conflict provider=%s", identity.provider)
        db.rollback()
        raced = _find_social_account(db, identity.provider, identity.provider_user_id)
        if raced is not None:
            raced.updated_at = utc_now()
            return _load_linked_user(db, raced, requested_role)
        raise _social_error(
            STATUS_CONFLICT,
            "SOCIAL_IDENTITY_CONFLICT",
            "This social account is already registered.",
        ) from None
    return user, role_name


_SOCIAL_REDIRECT_PATH = re.compile(r"^/(en|ar|es|fr)/auth/social/callback/?$")


def _cognito_token_endpoint() -> str:
    settings = get_settings()
    domain = (settings.cognito_domain or "").strip()
    domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    if not domain or "/" in domain:
        raise _SocialTokenError("not_configured")
    return f"https://{domain}/oauth2/token"


def _allowed_social_redirect(redirect_uri: str) -> bool:
    parsed = urllib.parse.urlparse(redirect_uri.strip())
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if parsed.query or parsed.fragment:
        return False
    return _SOCIAL_REDIRECT_PATH.fullmatch(parsed.path) is not None


def exchange_cognito_authorization_code(*, code: str, code_verifier: str, redirect_uri: str) -> str:
    """Exchange a hosted-UI code for the Cognito ID token. The client secret stays here."""
    settings = get_settings()
    client_id = (settings.cognito_app_client_id or "").strip()
    client_secret = (settings.cognito_app_client_secret or "").strip()
    authorization_code = code.strip()
    verifier = code_verifier.strip()
    callback = redirect_uri.strip()
    if (
        not client_id
        or not client_secret
        or not authorization_code
        or not verifier
        or len(authorization_code) > 2048
        or len(verifier) > 128
        or not _allowed_social_redirect(callback)
    ):
        raise _social_error(
            STATUS_BAD_REQUEST,
            "SOCIAL_TOKEN_MISSING",
            "A provider identity token is required.",
        )
    try:
        token_url = _cognito_token_endpoint()
    except _SocialTokenError as exc:
        _raise_token_error(exc)
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": authorization_code,
            "redirect_uri": callback,
            "code_verifier": verifier,
        }
    ).encode()
    request = urllib.request.Request(
        token_url,
        data=form,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    timeout = max(settings.social_provider_http_timeout_seconds, 1)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            error_payload = json.loads(raw)
        except json.JSONDecodeError:
            error_payload = {}
        provider_error = error_payload.get("error") if isinstance(error_payload, dict) else ""
        logger.warning("cognito_code_exchange_rejected reason=%s", provider_error or "invalid")
        if provider_error == "invalid_grant":
            raise _social_error(
                STATUS_UNAUTHORIZED,
                "SOCIAL_TOKEN_EXPIRED",
                "Social sign-in token has expired.",
            ) from None
        if provider_error == "invalid_client":
            raise _social_error(
                STATUS_SERVICE_UNAVAILABLE,
                "SOCIAL_PROVIDER_NOT_CONFIGURED",
                "Social sign-in is not configured for this provider.",
            ) from None
        raise _social_error(
            STATUS_UNAUTHORIZED,
            "SOCIAL_TOKEN_INVALID",
            "Social sign-in token is invalid.",
        ) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("cognito_code_exchange_unavailable error_type=%s", type(exc).__name__)
        raise _social_error(
            STATUS_SERVICE_UNAVAILABLE,
            "SOCIAL_PROVIDER_UNAVAILABLE",
            "Social sign-in provider could not be reached.",
        ) from None
    id_token = payload.get("id_token") if isinstance(payload, dict) else ""
    if not isinstance(id_token, str) or not id_token.strip() or len(id_token) > _MAX_TOKEN_LENGTH:
        raise _social_error(
            STATUS_UNAUTHORIZED,
            "SOCIAL_TOKEN_MISSING",
            "A provider identity token is required.",
        )
    return id_token.strip()


def authenticate_social(
    db: Session,
    *,
    provider: str,
    id_token: str | None = None,
    access_token: str | None = None,
    role: str | None = None,
) -> tuple[User, str | None]:
    """Sign in a mapped social identity or create a User/Owner account.

    Returns the MLS user and the database role to place first in the session
    token. The requested role is never stored over an existing account role.
    """
    identity = verify_social_identity(provider=provider, id_token=id_token, access_token=access_token)
    linked = _find_social_account(db, identity.provider, identity.provider_user_id)
    if linked is not None:
        linked.updated_at = utc_now()
        user, role_name = _load_linked_user(db, linked, role)
        _bind_cognito_sub(user, identity)
        return user, role_name

    if identity.cognito_sub:
        existing_cognito_user = _find_user_by_cognito_sub(db, identity.cognito_sub)
        if existing_cognito_user is not None:
            return _link_cognito_user(db, existing_cognito_user, identity, role)

    email = _reject_incomplete_profile(identity)
    if find_user_by_username(db, email):
        raise _email_already_registered()

    signup_role = _requested_social_role(role, required=True)
    assert signup_role is not None
    try:
        user = create_user(
            db,
            full_name=identity.full_name,
            email=email,
            phone_number=None,
            password=None,
            role=signup_role,
            is_active=True,
        )
        user.is_email_verified = True
        user.is_phone_verified = False
        user.phone_number = None
        _bind_cognito_sub(user, identity)
        db.add(_new_social_account(user, identity))
        db.flush()
    except IntegrityError:
        logger.warning("social_identity_conflict provider=%s", identity.provider)
        db.rollback()
        raced = _find_social_account(db, identity.provider, identity.provider_user_id)
        if raced is not None:
            raced.updated_at = utc_now()
            return _load_linked_user(db, raced, role)
        if identity.cognito_sub:
            existing_cognito_user = _find_user_by_cognito_sub(db, identity.cognito_sub)
            if existing_cognito_user is not None:
                return _link_cognito_user(db, existing_cognito_user, identity, role)
        if find_user_by_username(db, email):
            raise _email_already_registered() from None
        raise _social_error(
            STATUS_CONFLICT,
            "SOCIAL_IDENTITY_CONFLICT",
            "This social account is already registered.",
        ) from None
    return user, signup_role
