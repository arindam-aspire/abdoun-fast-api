from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import quote, unquote, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

_URL_KEYS = {
    "url",
    "file_url",
    "fileUrl",
    "thumb_url",
    "thumbUrl",
    "document_url",
    "documentUrl",
    "identity_document_url",
    "identityDocumentUrl",
    "logo_url",
    "logoUrl",
    "legal_document_s3_link",
    "legalDocumentS3Link",
}


def s3_object_url(bucket: str, region: str, object_key: str) -> str:
    encoded_key = quote(object_key, safe="/")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"


def generate_presigned_put_url(object_key: str) -> dict[str, Any] | None:
    """
    Generate a PUT presigned upload for a private bucket object.

    Returns upload_url, object_key, file_url (canonical storage URL), and
    readable_url / signed_read_url (GET presign for preview). None when S3 is
    not configured (caller should use a local/dev fallback).
    """
    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    region = (settings.aws_region or "us-west-2").strip().strip("\"'") or "us-west-2"
    if not bucket:
        return None

    try:
        upload_url = _s3_client().generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=settings.media_upload_presign_expires_seconds,
            HttpMethod="PUT",
        )
    except (BotoCoreError, ClientError):
        return None

    file_url = s3_object_url(bucket, region, object_key)
    readable_url = resolve_readable_media_url(file_url) or file_url
    return {
        "upload_url": upload_url,
        "object_key": object_key,
        "file_url": file_url,
        "readable_url": readable_url,
        "signed_read_url": readable_url,
        "expires_in": settings.media_upload_presign_expires_seconds,
        "readable_expires_in": settings.media_url_presign_expires_seconds,
    }

_URL_KEYS = {
    "url",
    "file_url",
    "fileUrl",
    "thumb_url",
    "thumbUrl",
    "document_url",
    "documentUrl",
    "identity_document_url",
    "identityDocumentUrl",
    "logo_url",
    "logoUrl",
    "legal_document_s3_link",
    "legalDocumentS3Link",
}


def _is_s3_hostname(hostname: str) -> bool:
    return hostname == "s3.amazonaws.com" or ".s3." in hostname or hostname.endswith(".s3.amazonaws.com")


def _object_key_from_s3_url(url: str, bucket: str) -> str | None:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if parsed.scheme not in {"http", "https"} or not _is_s3_hostname(hostname):
        return None

    if hostname == "s3.amazonaws.com" or hostname.startswith("s3."):
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) != 2 or parts[0] != bucket:
            return None
        return unquote(parts[1]) or None

    bucket_prefix = f"{bucket}."
    if not hostname.startswith(bucket_prefix):
        return None

    return unquote(parsed.path.lstrip("/")) or None


@lru_cache
def _s3_client():
    settings = get_settings()
    region = (settings.aws_region or "us-west-2").strip().strip("\"'") or "us-west-2"
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        ),
    )


def canonicalize_media_url(url: str | None) -> str | None:
    """Strip signature query params so only the stable object URL is stored."""
    if not url:
        return url

    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    if not bucket:
        return url

    object_key = _object_key_from_s3_url(url, bucket)
    if not object_key:
        # Drop query string even for unknown hosts if it looks like an Amz signature URL.
        parsed = urlparse(url)
        if parsed.query and "X-Amz-" in parsed.query:
            return parsed._replace(query="", fragment="").geturl()
        return url

    region = (settings.aws_region or "us-west-2").strip().strip("\"'") or "us-west-2"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"


def resolve_readable_media_url(url: str | None) -> str | None:
    """Return a short-lived GET-presigned URL for private S3 objects."""
    if not url:
        return url

    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")

    if not settings.media_url_presign_enabled or not bucket:
        return canonicalize_media_url(url) or url

    object_key = _object_key_from_s3_url(url, bucket)
    if not object_key:
        return url

    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=settings.media_url_presign_expires_seconds,
        )
    except (BotoCoreError, ClientError):
        return canonicalize_media_url(url) or url


def with_readable_media_urls(value: Any) -> Any:
    """Deep-copy payload-like structures and replace media URL fields with GET-presigned URLs."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _URL_KEYS and isinstance(item, str):
                out[key] = resolve_readable_media_url(item)
            else:
                out[key] = with_readable_media_urls(item)
        return out
    if isinstance(value, list):
        return [with_readable_media_urls(item) for item in value]
    return value


def with_canonical_media_urls(value: Any) -> Any:
    """Deep-copy and strip signature query params from stored media URL fields."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _URL_KEYS and isinstance(item, str):
                out[key] = canonicalize_media_url(item) or item
            else:
                out[key] = with_canonical_media_urls(item)
        return out
    if isinstance(value, list):
        return [with_canonical_media_urls(item) for item in value]
    return value
