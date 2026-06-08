"""Convert stored S3-style URLs in API responses to presigned GET URLs (private bucket)."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.schemas.property import PropertyDetail, PropertyMediaStructured, PropertySearchResult, PropertySearchResultExtended
from app.schemas.agency import (
    AgencyDocumentUploadResponse,
    AgencyLegalDocumentUploadData,
    AgencyLogoUploadResponse,
    AgencyResponse,
)
from app.schemas.user import ProfilePictureUploadData, UserResponse
from app.services.s3_service import S3Service
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.s3_stored_url import extract_s3_object_key, looks_like_existing_aws_presigned_url


_PENDING_LEGAL_DOCUMENT = "__pending_legal_document_upload__"


class MediaUrlSigner:
    """Reusable signing for any stored URL that maps to this app's S3 bucket."""

    def __init__(self, s3_service: S3Service, settings: Settings | None = None) -> None:
        self._s3 = s3_service
        self._settings = settings or get_settings()

    def sign_optional_url(self, url: str | None) -> str | None:
        """Return presigned GET URL for our bucket objects; pass through external URLs; None if empty."""
        if url is None:
            return None
        u = str(url).strip()
        if not u:
            return None
        if looks_like_existing_aws_presigned_url(u):
            return u
        key = extract_s3_object_key(u, self._settings)
        if key is None:
            return u
        try:
            return self._s3.generate_presigned_get_url(
                key=key,
                expires_in=self._settings.aws_s3_presigned_get_expiry_seconds,
            )
        except Exception as exc:  # pragma: no cover - boto/network
            api_logger.warning(
                format_log_message(
                    LogMessages.MediaUrlSigner.PRESIGNED_GET_FAILED,
                    error=str(exc),
                )
            )
            return u

    def apply_user_response(self, user: UserResponse) -> None:
        user.profile_picture_url = self.sign_optional_url(user.profile_picture_url)

    def user_response_from_orm(self, user_orm: object) -> UserResponse:
        """Build ``UserResponse`` from ORM user and sign ``profile_picture_url``."""
        resp = UserResponse.model_validate(user_orm)
        self.apply_user_response(resp)
        return resp

    def apply_profile_picture_upload_data(self, data: ProfilePictureUploadData) -> None:
        """Sign stored public URL only; leave presigned PUT ``upload_url`` unchanged."""
        orig = data.profile_picture_url
        signed = self.sign_optional_url(orig)
        data.profile_picture_url = signed if signed is not None else orig

    def apply_agency_response(self, agency: AgencyResponse) -> None:
        """Replace stored public S3 URLs with presigned GET for private bucket downloads."""
        link = (agency.legal_document_s3_link or "").strip()
        if link and link != _PENDING_LEGAL_DOCUMENT:
            signed = self.sign_optional_url(link)
            if signed is not None:
                agency.legal_document_s3_link = signed
        if agency.logo_url:
            signed_logo = self.sign_optional_url(agency.logo_url)
            if signed_logo is not None:
                agency.logo_url = signed_logo

    def apply_agency_logo_upload_response(self, data: AgencyLogoUploadResponse) -> None:
        """Sign stored public URL only; leave presigned PUT ``upload_url`` unchanged."""
        orig = data.logo_url
        signed = self.sign_optional_url(orig)
        data.logo_url = signed if signed is not None else orig

    def apply_agency_legal_document_upload_data(self, data: AgencyLegalDocumentUploadData) -> None:
        """Sign stored public URL only; leave presigned PUT ``upload_url`` unchanged."""
        orig = data.legal_document_s3_link
        signed = self.sign_optional_url(orig)
        data.legal_document_s3_link = signed if signed is not None else orig

    def apply_agency_document_upload_response(self, data: AgencyDocumentUploadResponse) -> None:
        """Same as profile-picture upload: sign canonical URL, not the PUT presign."""
        orig = data.legal_document_s3_link
        signed = self.sign_optional_url(orig)
        data.legal_document_s3_link = signed if signed is not None else orig

    def sign_media_structured(self, media: PropertyMediaStructured | None) -> None:
        if media is None:
            return
        media.thumbnail = self.sign_optional_url(media.thumbnail)
        media.virtual_tour_url = self.sign_optional_url(media.virtual_tour_url)
        for coll in (media.images, media.videos, media.floor_plan_images, media.documents):
            for it in coll:
                signed = self.sign_optional_url(it.url)
                if signed is not None:
                    it.url = signed
                st = self.sign_optional_url(it.thumb_url)
                it.thumb_url = st

    def sign_property_detail(self, detail: PropertyDetail) -> None:
        if detail.url:
            detail.url = self.sign_optional_url(detail.url)
        self.sign_media_structured(detail.media)
        if detail.agent and detail.agent.photo:
            detail.agent.photo = self.sign_optional_url(detail.agent.photo)
        # owner mock has no image field in schema beyond basic info

    def sign_search_result_extended(self, row: PropertySearchResultExtended) -> None:
        self.sign_media_structured(row.media)

    def sign_search_result(self, row: PropertySearchResult) -> None:
        row.thumbnail = self.sign_optional_url(row.thumbnail)
