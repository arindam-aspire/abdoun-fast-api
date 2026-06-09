"""Dependencies for GET /properties/my-listings."""

from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import get_user_roles
from app.db.session import get_db
from app.models.user import User
from app.repositories.property_repository import PropertyRepository
from app.services.my_listings_service import MyListingsService
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.status_codes import HTTPStatus

MyListingsScope = Literal["admin", "agent"]


@dataclass(frozen=True)
class MyListingsAuth:
    user: User
    scope: MyListingsScope


def get_my_listings_service(db: Session = Depends(get_db)) -> MyListingsService:
    return MyListingsService(property_repository=PropertyRepository(db))


def require_agent_or_admin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyListingsAuth:
    """Allow agents (own listings) or admins/super_admins (all listings)."""
    roles = get_user_roles(user, db)
    if UserRoles.ADMIN in roles or UserRoles.SUPER_ADMIN in roles:
        return MyListingsAuth(user=user, scope="admin")
    if UserRoles.AGENT in roles:
        return MyListingsAuth(user=user, scope="agent")
    raise HTTPException(
        status_code=HTTPStatus.FORBIDDEN,
        detail=ErrorMessages.MY_LISTINGS_ACCESS_DENIED,
    )
