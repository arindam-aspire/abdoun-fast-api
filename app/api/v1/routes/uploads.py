"""Upload helper endpoints for presigned URL workflow."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps.security import get_current_user
from app.api.v1.deps.uploads import get_upload_service
from app.models.user import User
from app.schemas.uploads import PresignedUploadData, PresignedUploadRequest
from app.services.upload_service import UploadService
from app.utils.responses import StandardResponse, create_success_response

router = APIRouter()


@router.post("/presigned-url", response_model=StandardResponse[PresignedUploadData])
def get_presigned_upload_url(
    body: PresignedUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UploadService, Depends(get_upload_service)],
):
    """Return presigned upload for direct S3 PUT.

    Send exactly one of ``submission_id`` (saved draft) or ``draft_client_id`` (client UUID before any submission row).
    All calls require an authenticated user.
    """
    data = service.generate_presigned_upload(body=body, user=current_user)
    return create_success_response(data=data, message=None)

