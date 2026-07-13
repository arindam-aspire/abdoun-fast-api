from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.localization import normalize_locale
from app.core.tokens import verify_token
from app.db.session import get_db
from app.models.live_schema import Role, User, UserRole
from app.services.user_agencies import primary_agency_id_for_context
from app.utils.status_codes import STATUS_FORBIDDEN, STATUS_UNAUTHORIZED


DBSessionDep = Annotated[Session, Depends(get_db)]


def has_authorization_header(authorization: str | None) -> bool:
    if not authorization or not authorization.strip():
        return False
    if not authorization.lower().startswith("bearer "):
        return False
    return bool(authorization.split(" ", 1)[1].strip())


def is_authenticated_request(authorization: str | None, user_id: UUID | None) -> bool:
    return has_authorization_header(authorization) and user_id is not None


@dataclass(frozen=True)
class RequestContext:
    locale: str
    user_id: UUID | None = None
    agency_id: UUID | None = None
    roles: tuple[str, ...] = ()


def get_request_context(
    db: DBSessionDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    accept_language: Annotated[str | None, Header(alias="Accept-Language")] = None,
) -> RequestContext:
    locale = normalize_locale(accept_language)
    if not authorization or not authorization.lower().startswith("bearer "):
        return RequestContext(locale=locale)

    token = authorization.split(" ", 1)[1].strip()
    payload = verify_token(token, expected_type="access")
    if not payload:
        return RequestContext(locale=locale)

    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        return RequestContext(locale=locale)

    user = db.get(User, user_id)
    if not user or not user.is_active:
        return RequestContext(locale=locale)

    roles = tuple(
        db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
            .order_by(Role.name)
        ).scalars().all()
    )
    return RequestContext(
        locale=locale,
        user_id=user.id,
        agency_id=primary_agency_id_for_context(db, user, roles),
        roles=roles,
    )


RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]


def require_authenticated_user(context: RequestContextDep) -> RequestContext:
    if context.user_id is None:
        raise HTTPException(
            status_code=STATUS_UNAUTHORIZED,
            detail="Authentication is required",
        )
    return context


def require_any_role(*allowed_roles: str):
    normalized_allowed = {role.casefold() for role in allowed_roles}

    def dependency(context: RequestContextDep) -> RequestContext:
        if not context.roles:
            raise HTTPException(
                status_code=STATUS_UNAUTHORIZED,
                detail="Authentication is required",
            )

        user_roles = {role.casefold() for role in context.roles}
        if "admin" in user_roles:
            user_roles.add("agency")
        if "agency" in user_roles:
            user_roles.add("admin")
        if "agency_admin" in user_roles:
            user_roles.update({"admin", "agency"})
        if user_roles.isdisjoint(normalized_allowed):
            raise HTTPException(
                status_code=STATUS_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return context

    return dependency
