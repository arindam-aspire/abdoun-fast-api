"""Password hashing and legacy agency JWT decode for existing sessions."""
from __future__ import annotations

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.utils.constants import UserRoles


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
AGENCY_JWT_ALGORITHM = "HS256"
AGENCY_AUTH_PROVIDER = "agency"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def decode_agency_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            get_settings().agency_jwt_secret,
            algorithms=[AGENCY_JWT_ALGORITHM],
        )
    except Exception:
        return None
    if payload.get("auth_provider") != AGENCY_AUTH_PROVIDER:
        return None
    if payload.get("token_use") != "access":
        return None
    if payload.get("role") not in {UserRoles.SUPER_ADMIN, UserRoles.ADMIN}:
        return None
    return payload
