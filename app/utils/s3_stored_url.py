"""Parse stored S3 public-style URLs (or raw keys) into bucket object keys for presigned GET."""

from __future__ import annotations

from urllib.parse import urlparse, unquote

from app.core.config import Settings


def looks_like_existing_aws_presigned_url(url: str) -> bool:
    """True if URL query already contains AWS signing params (PUT or GET presigned).

    Avoid re-processing these when callers pass a presigned PUT URL by mistake.
    """
    lower = url.lower()
    if "x-amz-algorithm=" in lower or "x-amz-credential=" in lower or "x-amz-signature=" in lower:
        return True
    if "awsaccesskeyid=" in lower and "signature=" in lower:
        return True
    return False


def extract_s3_object_key(stored: str, settings: Settings) -> str | None:
    """Return S3 object key if *stored* is a URL/key we own; otherwise None (external / unknown).

    Supports:
    - Raw keys: ``users/...``, ``properties/...``, ``drafts/...``
    - ``AWS_S3_PUBLIC_BASE_URL`` + key
    - Virtual-hosted: ``https://{bucket}.s3.{region}.amazonaws.com/{key}``
    - Legacy: ``https://{bucket}.s3.amazonaws.com/{key}``
    - Path-style: ``https://s3.{region}.amazonaws.com/{bucket}/{key}`` and dualstack variant
    - Custom endpoint: ``{endpoint}/{bucket}/{key}``
    """
    raw = (stored or "").strip()
    if not raw:
        return None

    if looks_like_existing_aws_presigned_url(raw):
        return None

    if not raw.lower().startswith(("http://", "https://")):
        for prefix in ("users/", "properties/", "drafts/"):
            if raw.startswith(prefix) or raw.startswith("/" + prefix):
                return raw.lstrip("/")
        return None

    parsed = urlparse(raw)
    path = unquote(parsed.path or "").lstrip("/")
    bucket = (settings.aws_s3_bucket or "").strip()
    if not bucket:
        return None

    base = (settings.aws_s3_public_base_url or "").strip().rstrip("/")
    if base and raw.startswith(base + "/"):
        return raw[len(base) + 1 :].split("?")[0] or None

    host = (parsed.hostname or "").lower()
    netloc = (parsed.netloc or "").lower()

    # https://bucket.s3.region.amazonaws.com/key OR s3.dualstack.region.amazonaws.com
    if host == f"{bucket.lower()}.s3.{settings.aws_region.lower()}.amazonaws.com":
        return path.split("?")[0] or None
    if host == f"{bucket.lower()}.s3.dualstack.{settings.aws_region.lower()}.amazonaws.com":
        return path.split("?")[0] or None
    if host == f"{bucket.lower()}.s3.amazonaws.com":
        return path.split("?")[0] or None

    # Path-style: s3.region.amazonaws.com/bucket/key
    for suffix in (
        f"s3.{settings.aws_region.lower()}.amazonaws.com",
        f"s3.dualstack.{settings.aws_region.lower()}.amazonaws.com",
    ):
        if host == suffix:
            parts = path.split("/", 1)
            if len(parts) == 2 and parts[0] == bucket:
                return parts[1].split("?")[0] or None
            return None

    ep = (settings.aws_s3_endpoint_url or "").strip().rstrip("/")
    if ep:
        # http://localhost:9000/bucket/key
        if raw.startswith(f"{ep}/{bucket}/"):
            return raw[len(f"{ep}/{bucket}/") :].split("?")[0] or None

    return None
