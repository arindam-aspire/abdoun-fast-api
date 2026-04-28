"""Dependencies for admin property endpoints."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_admin_repository import PropertyAdminRepository
from app.services.property_admin_service import PropertyAdminService


def get_property_admin_service(db: Session = Depends(get_db)) -> PropertyAdminService:
    return PropertyAdminService(PropertyAdminRepository(db))

