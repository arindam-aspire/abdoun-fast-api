from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

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

_REDACT_MARKERS = (
    "X-Amz-Credential=",
    "X-Amz-Signature=",
    "AWSAccessKeyId=",
    "Signature=",
)


def s3_object_url(bucket: str, region: str, object_key: str) -> str:
    encoded_key = quote(object_key, safe="/")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"


def generate_presigned_put_url(object_key: str, *, content_type: str | None = None) -> dict[str, Any] | None:
    """
    Generate a PUT presigned upload for a private bucket object.

    Content-Type is intentionally not signed so browsers can PUT with or
    without that header. Returns upload_url, object_key, file_url (canonical
    storage URL), and readable_url / signed_read_url (GET presign for preview).
    None when S3 is not configured (caller should use a local/dev fallback).
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
    except (BotoCoreError, ClientError) as exc:
        log_s3_error("generate_presigned_put", exc, object_key=object_key)
        return None

    file_url = s3_object_url(bucket, region, object_key)
    readable_url = resolve_readable_media_url(file_url) or file_url
    return {
        "upload_url": upload_url,
        "object_key": object_key,
        "file_url": file_url,
        "readable_url": readable_url,
        "signed_read_url": readable_url,
        "upload_http_method": "PUT",
        "view_http_method": "GET",
        "expires_in": settings.media_upload_presign_expires_seconds,
        "readable_expires_in": settings.media_url_presign_expires_seconds,
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


def _redact_secrets(text: str) -> str:
    redacted = text.replace("\n", " ").strip()
    for marker in _REDACT_MARKERS:
        if marker in redacted:
            prefix, remainder = redacted.split(marker, 1)
            remainder = remainder.split(" ", 1)[-1] if " " in remainder else ""
            redacted = f"{prefix}{marker}[REDACTED] {remainder}".strip()
    return redacted[:500]


def parse_s3_error_xml(body: str) -> tuple[str | None, str | None]:
    """Return (Code, Message) from an S3 XML error body without exposing signatures."""
    if not body or "<" not in body:
        return None, None
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None, None

    code = None
    message = None
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "Code" and node.text:
            code = node.text.strip()
        elif tag == "Message" and node.text:
            message = _redact_secrets(node.text.strip())
    return code, message


def log_s3_error(step: str, error: BaseException, *, object_key: str | None = None, body: str | None = None) -> None:
    """Log S3 Error Code/Message only; never log credentials or full presigned URLs."""
    code: str | None = None
    message: str | None = None
    http_status: int | str | None = None

    if isinstance(error, ClientError):
        details = error.response.get("Error") or {}
        code = details.get("Code")
        raw_message = details.get("Message")
        message = _redact_secrets(str(raw_message)) if raw_message else None
        http_status = (error.response.get("ResponseMetadata") or {}).get("HTTPStatusCode")

    xml_code, xml_message = parse_s3_error_xml(body or "")
    code = code or xml_code or type(error).__name__
    message = message or xml_message or _redact_secrets(str(error))
    key_hint = object_key.rsplit("/", 1)[-1] if object_key else None
    logger.warning(
        "s3_error step=%s code=%s http_status=%s key=%s message=%s",
        step,
        code,
        http_status,
        key_hint,
        message,
    )


def probe_s3_object_access(url: str | None) -> None:
    """HEAD the object and log the S3 XML/API error code if access fails."""
    if not url:
        return

    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    if not bucket:
        return

    object_key = _object_key_from_s3_url(url, bucket)
    if not object_key:
        return

    try:
        _s3_client().head_object(Bucket=bucket, Key=object_key)
    except ClientError as exc:
        log_s3_error("head_object", exc, object_key=object_key)
    except BotoCoreError as exc:
        log_s3_error("head_object", exc, object_key=object_key)


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
    return s3_object_url(bucket, region, object_key)


def generate_presigned_get_url(object_key: str) -> str | None:
    """Generate a short-lived GET (get_object) presigned URL. Does not alter query params later."""
    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    if not settings.media_url_presign_enabled or not bucket:
        return None

    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=settings.media_url_presign_expires_seconds,
            HttpMethod="GET",
        )
    except (BotoCoreError, ClientError) as exc:
        log_s3_error("generate_presigned_get", exc, object_key=object_key)
        return None


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

    return generate_presigned_get_url(object_key) or canonicalize_media_url(url) or url


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
