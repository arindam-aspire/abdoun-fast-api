from starlette.formparsers import MultiPartParser

from app.core.config import Settings
from app.utils.multipart_limits import (
    configure_multipart_limits,
    multipart_max_upload_bytes,
    property_image_multipart_max_bytes,
)


def test_property_image_multipart_max_bytes_uses_image_limit_only():
    settings = Settings(
        property_image_max_size_mb=5,
        property_document_max_size_mb=20,
        property_video_max_size_mb=100,
    )
    assert property_image_multipart_max_bytes(settings) == 5 * 1024 * 1024


def test_multipart_max_upload_bytes_uses_largest_upload_limit():
    settings = Settings(
        property_image_max_size_mb=20,
        property_document_max_size_mb=20,
        property_video_max_size_mb=100,
    )
    assert multipart_max_upload_bytes(settings) == 100 * 1024 * 1024


def test_configure_multipart_limits_sets_starlette_parser():
    original = MultiPartParser.max_file_size
    try:
        settings = Settings(
            property_image_max_size_mb=20,
            property_document_max_size_mb=20,
            property_video_max_size_mb=20,
        )
        expected = configure_multipart_limits(settings)
        assert MultiPartParser.max_file_size == expected == 20 * 1024 * 1024
    finally:
        MultiPartParser.max_file_size = original
