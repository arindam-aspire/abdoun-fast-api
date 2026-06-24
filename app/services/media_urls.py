from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings


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
        return parts[1]

    bucket_prefix = f"{bucket}."
    if not hostname.startswith(bucket_prefix):
        return None

    return parsed.path.lstrip("/") or None


@lru_cache
def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(signature_version="s3v4"),
    )


def resolve_readable_media_url(url: str | None) -> str | None:
    if not url:
        return url

    settings = get_settings()
    bucket = settings.aws_s3_bucket

    if not settings.media_url_presign_enabled or not bucket:
        return url

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
        return url
