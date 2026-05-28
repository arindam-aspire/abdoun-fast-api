"""API-issued access JWTs returned in login ``access_token`` (Cognito refresh/id tokens unchanged)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import jwt

from app.core.config import get_settings
from app.models.user import Role, User
from app.utils.constants import UserRoles


AUTH_ACCESS_JWT_ALGORITHM = "HS256"
AUTH_ACCESS_PROVIDER = "abdoun_api"

# Prefer highest-privilege role when multiple are assigned.
_ROLE_PRIORITY: tuple[str, ...] = (
    UserRoles.SUPER_ADMIN,
    UserRoles.ADMIN,
    UserRoles.AGENT,
    UserRoles.REGISTERED_USER,
)


def primary_role(user: User) -> Role | None:
    """Pick a single role for the JWT claim (null when user has no roles)."""
    roles: list[Role] = list(getattr(user, "roles", None) or [])
    if not roles:
        return None
    by_name = {role.name: role for role in roles}
    for name in _ROLE_PRIORITY:
        if name in by_name:
            return by_name[name]
    return roles[0]


def role_claim(role: Role | None) -> dict[str, str] | None:
    if role is None:
        return None
    return {"role_id": str(role.id), "role_name": role.name}


def jwt_subject(user: User) -> str:
    """JWT ``sub`` claim: Cognito user id when present, else DB id (legacy fallback)."""
    cognito_sub = (getattr(user, "cognito_sub", None) or "").strip()
    return cognito_sub or str(user.id)


def cognito_refresh_username(user: User) -> str:
    """Cognito USERNAME for refresh SECRET_HASH (for this client: Cognito ``sub``)."""
    cognito_sub = (getattr(user, "cognito_sub", None) or "").strip()
    if cognito_sub:
        return cognito_sub
    # Defensive fallback for malformed rows; refresh will still fail if Cognito expects sub.
    return str(user.email).strip().lower()


def build_access_token_payload(*, user: User, expires_in: int) -> dict[str, Any]:
    """Build JWT claims for login/refresh ``access_token`` (not returned as extra API fields)."""
    now = datetime.now(timezone.utc)
    role = role_claim(primary_role(user))
    payload: dict[str, Any] = {
        "sub": jwt_subject(user),
        "user_id": str(user.id),
        "email": user.email,
        "token_use": "access",
        "auth_provider": AUTH_ACCESS_PROVIDER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    if role is not None:
        payload["role"] = role
    return payload


def create_auth_access_token(*, user: User, expires_in: int) -> str:
    """Sign enriched access token; ``expires_in`` mirrors Cognito ``ExpiresIn`` from auth result."""
    payload = build_access_token_payload(user=user, expires_in=expires_in)
    return jwt.encode(
        payload,
        get_settings().agency_jwt_secret,
        algorithm=AUTH_ACCESS_JWT_ALGORITHM,
    )


def decode_auth_access_token(token: str) -> dict[str, Any] | None:
    """Verify API-issued access JWT; returns payload or None."""
    try:
        payload = jwt.decode(
            token,
            get_settings().agency_jwt_secret,
            algorithms=[AUTH_ACCESS_JWT_ALGORITHM],
        )
    except Exception:
        return None
    if payload.get("auth_provider") != AUTH_ACCESS_PROVIDER:
        return None
    if payload.get("token_use") != "access":
        return None
    if not payload.get("sub"):
        return None
    return payload


def role_from_token_payload(payload: dict[str, Any]) -> dict[str, str] | None:
    """Extract nested role claim with null-safety for callers (e.g. auth dependencies)."""
    role = payload.get("role")
    if not isinstance(role, dict):
        return None
    role_id = role.get("role_id")
    role_name = role.get("role_name")
    if not role_id or not role_name:
        return None
    return {"role_id": str(role_id), "role_name": str(role_name)}


def is_auth_access_token(token: str) -> bool:
    return decode_auth_access_token(token) is not None


def parse_user_id_from_payload(payload: dict[str, Any]) -> UUID | None:
    """Resolve DB user id from API token (``user_id`` claim, then legacy ``sub`` as UUID)."""
    raw_user_id = payload.get("user_id")
    if raw_user_id:
        try:
            return UUID(str(raw_user_id))
        except (ValueError, TypeError):
            pass
    raw_sub = payload.get("sub")
    if not raw_sub:
        return None
    try:
        return UUID(str(raw_sub))
    except (ValueError, TypeError):
        return None


def cognito_sub_from_payload(payload: dict[str, Any]) -> str | None:
    """Cognito subject from ``sub`` when it is not a DB UUID (used after refresh username mapping)."""
    raw_sub = (payload.get("sub") or "").strip()
    if not raw_sub:
        return None
    try:
        UUID(raw_sub)
        return None
    except (ValueError, TypeError):
        return raw_sub
