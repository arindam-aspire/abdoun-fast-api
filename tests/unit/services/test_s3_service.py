"""Unit tests for S3 service helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.s3_service import S3Service


def _settings(*, endpoint_url: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        aws_region="us-east-1",
        aws_access_key_id="k",
        aws_secret_access_key="s",
        aws_s3_bucket="abdoun-bucket",
        aws_s3_endpoint_url=endpoint_url,
        aws_s3_public_base_url=None,
        aws_s3_presigned_expiry=900,
        aws_s3_presigned_get_expiry_seconds=3600,
    )


def test_build_client_kwargs_keeps_endpoint_optional() -> None:
    kwargs_without = S3Service._build_client_kwargs(_settings(endpoint_url=None))
    kwargs_with = S3Service._build_client_kwargs(_settings(endpoint_url="https://s3.custom.local"))
    assert "endpoint_url" not in kwargs_without
    assert kwargs_with["endpoint_url"] == "https://s3.custom.local"


def test_put_object_uploads_bytes() -> None:
    client = MagicMock()
    with patch("app.services.s3_service.boto3.client", return_value=client):
        service = S3Service(_settings(endpoint_url=None))
        service.put_object(key="drafts/a.jpg", body=b"bytes", content_type="image/jpeg")
    client.put_object.assert_called_once_with(
        Bucket="abdoun-bucket",
        Key="drafts/a.jpg",
        Body=b"bytes",
        ContentType="image/jpeg",
    )


def test_build_public_url_uses_aws_or_endpoint() -> None:
    aws_service = S3Service(_settings(endpoint_url=None))
    endpoint_service = S3Service(_settings(endpoint_url="https://s3.custom.local"))
    assert (
        aws_service.build_public_url("drafts/property-submissions/a/file.jpg")
        == "https://abdoun-bucket.s3.us-east-1.amazonaws.com/drafts/property-submissions/a/file.jpg"
    )
    assert (
        endpoint_service.build_public_url("drafts/property-submissions/a/file.jpg")
        == "https://s3.custom.local/abdoun-bucket/drafts/property-submissions/a/file.jpg"
    )

