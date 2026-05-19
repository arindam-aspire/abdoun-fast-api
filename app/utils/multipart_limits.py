"""Starlette multipart upload size limits (default is 1 MB per file part)."""

from __future__ import annotations

import inspect

from starlette.formparsers import MultiPartParser
from starlette.requests import Request

from app.core.config import Settings, get_settings


def multipart_max_upload_bytes(settings: Settings | None = None) -> int:
    """Largest allowed multipart file part, aligned with upload validation settings."""
    settings = settings or get_settings()
    max_mb = max(
        settings.property_image_max_size_mb,
        settings.property_document_max_size_mb,
        settings.property_video_max_size_mb,
    )
    return max_mb * 1024 * 1024


def configure_multipart_limits(settings: Settings | None = None) -> int:
    """Raise Starlette's default 1 MB multipart file part limit (call once at app startup)."""
    max_bytes = multipart_max_upload_bytes(settings)
    MultiPartParser.max_file_size = max_bytes
    return max_bytes


def property_image_multipart_max_bytes(settings: Settings | None = None) -> int:
    """Multipart part limit for property image upload endpoints (matches validation cap)."""
    settings = settings or get_settings()
    return settings.property_image_max_size_mb * 1024 * 1024


async def parse_property_image_form(request: Request, settings: Settings | None = None):
    """Parse multipart form data for property image uploads (5 MB default, env-configurable)."""
    max_bytes = property_image_multipart_max_bytes(settings)
    form_method = request.form
    if "max_part_size" in inspect.signature(form_method).parameters:
        return await form_method(max_part_size=max_bytes)
    original = MultiPartParser.max_file_size
    try:
        MultiPartParser.max_file_size = max_bytes
        return await form_method()
    finally:
        MultiPartParser.max_file_size = original
