"""Dependency providers for owner routes."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.owner_repository import OwnerRepository
from app.services.owner_service import OwnerService


def get_owner_repository(db: Session = Depends(get_db)) -> OwnerRepository:
    """Provide OwnerRepository bound to current request DB session."""
    return OwnerRepository(db)


def get_owner_service(repo: OwnerRepository = Depends(get_owner_repository)) -> OwnerService:
    """Provide OwnerService for owner and mapping CRUD endpoints."""
    return OwnerService(repo)
