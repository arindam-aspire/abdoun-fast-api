"""Verify configured S3 credentials with a temporary probe object.

This script intentionally does not print secrets or presigned URLs. It creates a
single object under ``codex-permission-probes/`` and deletes only that object.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import boto3
import requests
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from dotenv import load_dotenv


PROBE_PREFIX = "codex-permission-probes"
PROBE_BODY = b"Abdoun MLS S3 permission probe. Safe to delete.\n"
PROBE_CONTENT_TYPE = "text/plain"
PRESIGN_SECONDS = 300


def _clean_env(value: str | None, default: str = "") -> str:
    return (value or default).strip().strip("\"'")


def _redact_request_error(exc: BaseException) -> str:
    text = str(exc)
    for token in (
        "AWSAccessKeyId=",
        "X-Amz-Credential=",
        "Signature=",
        "X-Amz-Signature=",
    ):
        if token in text:
            text = text.split(token)[0] + token + "[REDACTED]"
    return text[:500]


def main() -> int:
    load_dotenv(Path.cwd() / ".env")

    bucket = _clean_env(os.getenv("AWS_S3_BUCKET"))
    region = _clean_env(
        os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    )

    print("S3 permission probe starting")
    print(f"bucket_configured={bool(bucket)} region_configured={bool(region)}")

    if not bucket:
        print("RESULT=FAIL reason=AWS_S3_BUCKET is not configured")
        return 2
    if not region:
        print("RESULT=FAIL reason=AWS_REGION is not configured")
        return 2

    session = boto3.session.Session(region_name=region)
    credentials = session.get_credentials()
    if credentials is None:
        print("RESULT=FAIL reason=No AWS credentials found in environment/profile")
        return 2

    credentials.get_frozen_credentials()
    print("credentials_loaded=True")

    s3 = session.client("s3", region_name=region)
    key = f"{PROBE_PREFIX}/{uuid.uuid4()}.txt"
    created = False

    try:
        put_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ContentType": PROBE_CONTENT_TYPE,
            },
            ExpiresIn=PRESIGN_SECONDS,
        )
        put_response = requests.put(
            put_url,
            data=PROBE_BODY,
            headers={"Content-Type": PROBE_CONTENT_TYPE},
            timeout=30,
        )
        print(f"put_via_presigned_status={put_response.status_code}")
        if put_response.status_code not in (200, 204):
            print(
                "RESULT=FAIL "
                f"step=presigned_put status={put_response.status_code} "
                f"body={put_response.text[:300]!r}"
            )
            return 3
        created = True

        head = s3.head_object(Bucket=bucket, Key=key)
        print(
            "head_object=OK "
            f"content_length={head.get('ContentLength')} "
            f"content_type={head.get('ContentType')}"
        )

        get_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=PRESIGN_SECONDS,
        )
        get_response = requests.get(get_url, timeout=30)
        print(
            f"get_via_presigned_status={get_response.status_code} "
            f"bytes={len(get_response.content)}"
        )
        if get_response.status_code != 200 or get_response.content != PROBE_BODY:
            print(
                "RESULT=FAIL "
                f"step=presigned_get status={get_response.status_code} "
                f"body={get_response.text[:300]!r}"
            )
            return 4

        s3.delete_object(Bucket=bucket, Key=key)
        print("delete_probe_object=OK")
        created = False

        print(
            "RESULT=PASS "
            "permissions=presigned_put,presigned_get,head_object,delete_probe_object"
        )
        return 0
    except (NoCredentialsError, PartialCredentialsError) as exc:
        print(f"RESULT=FAIL reason=credential_error type={type(exc).__name__}")
        return 2
    except requests.RequestException as exc:
        print(
            "RESULT=FAIL "
            f"reason=request_error type={type(exc).__name__} "
            f"message={_redact_request_error(exc)}"
        )
        return 6
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        message = exc.response.get("Error", {}).get("Message")
        print(f"RESULT=FAIL reason=aws_client_error code={code} message={message}")
        return 7
    finally:
        if created:
            try:
                s3.delete_object(Bucket=bucket, Key=key)
                print("cleanup_after_failure=OK")
            except Exception as exc:  # pragma: no cover - diagnostic fallback
                print(
                    "cleanup_after_failure=FAILED "
                    f"key={key} type={type(exc).__name__}"
                )


if __name__ == "__main__":
    sys.exit(main())
