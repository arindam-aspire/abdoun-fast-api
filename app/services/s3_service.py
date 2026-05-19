"""S3 utility service for presigned upload URL workflows."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.utils.status_codes import HTTPStatus
from fastapi import HTTPException


class S3Service:
    """Service wrapper for S3 operations used by upload workflows."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = boto3.client("s3", **self._build_client_kwargs(self._settings))

    @staticmethod
    def _build_client_kwargs(settings: Settings) -> dict[str, Any]:
        """Build boto3 client kwargs with optional endpoint override."""
        client_kwargs: dict[str, Any] = {
            "region_name": settings.aws_region,
        }
        if settings.aws_access_key_id:
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        if settings.aws_secret_access_key:
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        if settings.aws_s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.aws_s3_endpoint_url
        return client_kwargs

    def generate_presigned_upload_url(self, *, key: str, content_type: str, expires_in: int | None = None) -> str:
        """Generate a presigned PUT URL for direct browser/client uploads."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        expiry = expires_in or self._settings.aws_s3_presigned_expiry
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._settings.aws_s3_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expiry,
        )

    def generate_presigned_get_url(self, *, key: str, expires_in: int | None = None) -> str:
        """Generate a presigned GET URL so clients can read a private object."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        expiry = expires_in if expires_in is not None else self._settings.aws_s3_presigned_get_expiry_seconds
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._settings.aws_s3_bucket, "Key": key},
            ExpiresIn=expiry,
        )

    def build_public_url(self, key: str) -> str:
        """Build a public URL for object key based on configured strategy."""
        if self._settings.aws_s3_public_base_url:
            return f"{self._settings.aws_s3_public_base_url.rstrip('/')}/{key}"
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        if self._settings.aws_s3_endpoint_url:
            return f"{self._settings.aws_s3_endpoint_url.rstrip('/')}/{self._settings.aws_s3_bucket}/{key}"
        region = self._settings.aws_region
        return f"https://{self._settings.aws_s3_bucket}.s3.{region}.amazonaws.com/{key}"

    def copy_object(self, *, source_key: str, destination_key: str) -> None:
        """Copy an object within the configured bucket."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        self._client.copy_object(
            Bucket=self._settings.aws_s3_bucket,
            CopySource={"Bucket": self._settings.aws_s3_bucket, "Key": source_key},
            Key=destination_key,
        )

    def delete_object(self, *, key: str) -> None:
        """Delete object by key from the configured bucket."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        self._client.delete_object(Bucket=self._settings.aws_s3_bucket, Key=key)

    def object_exists(self, *, key: str) -> bool:
        """Return True if the object exists in the configured bucket."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        try:
            self._client.head_object(Bucket=self._settings.aws_s3_bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NotFound", "NoSuchKey"}:
                return False
            raise

    def get_object(self, *, key: str) -> tuple[bytes, str | None]:
        """Download object bytes and optional Content-Type from the configured bucket."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        try:
            response = self._client.get_object(Bucket=self._settings.aws_s3_bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Object not found in S3") from exc
            raise
        body = response["Body"].read()
        return body, response.get("ContentType")

    def put_object(self, *, key: str, body: bytes, content_type: str) -> None:
        """Upload object bytes to the configured bucket (overwrites existing key)."""
        if not self._settings.aws_s3_bucket:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="AWS_S3_BUCKET is not configured")
        self._client.put_object(
            Bucket=self._settings.aws_s3_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
