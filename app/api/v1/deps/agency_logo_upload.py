"""Dependency provider for agency logo presigned uploads."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps.uploads import get_s3_service
from app.db.session import get_db
from app.repositories.agency_repository import AgencyRepository
from app.services.agency_logo_upload_service import AgencyLogoUploadService
from app.services.s3_service import S3Service

from app.api.v1.deps.agency import DBSessionDep


def get_agency_logo_upload_service(
    db: DBSessionDep,
    s3: S3Service = Depends(get_s3_service),
) -> AgencyLogoUploadService:
    return AgencyLogoUploadService(AgencyRepository(db), s3_service=s3)


AgencyLogoUploadServiceDep = Annotated[AgencyLogoUploadService, Depends(get_agency_logo_upload_service)]
