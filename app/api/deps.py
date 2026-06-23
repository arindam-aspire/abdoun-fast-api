from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.localization import normalize_locale
from app.db.session import get_db
from app.utils.status_codes import STATUS_FORBIDDEN, STATUS_UNAUTHORIZED


DBSessionDep = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class RequestContext:
    locale: str
    user_id: UUID | None = None
    agency_id: UUID | None = None
    roles: tuple[str, ...] = ()


def get_request_context(
    accept_language: Annotated[str | None, Header(alias="Accept-Language")] = None,
) -> RequestContext:
    return RequestContext(locale=normalize_locale(accept_language))


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
        if user_roles.isdisjoint(normalized_allowed):
            raise HTTPException(
                status_code=STATUS_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return context

    return dependency
