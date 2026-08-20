from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.services import media_urls
from app.services.media_urls import (
    generate_presigned_get_url,
    parse_s3_error_xml,
    resolve_readable_media_url,
)


@pytest.fixture(autouse=True)
def clear_caches():
    get_settings.cache_clear()
    media_urls._s3_client.cache_clear()
    yield
    get_settings.cache_clear()
    media_urls._s3_client.cache_clear()


def _settings(**overrides: object) -> Settings:
    base = get_settings().model_dump()
    base.update(overrides)
    return Settings(**base)


def test_resolve_readable_media_url_signs_get_object(monkeypatch) -> None:
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = (
        "https://abdoun-dev-assets-usw2.s3.us-west-2.amazonaws.com/"
        "agency_legal_document/id/file.pdf?X-Amz-Signature=abc"
    )
    monkeypatch.setattr(
        media_urls,
        "get_settings",
        lambda: _settings(
            aws_s3_bucket="abdoun-dev-assets-usw2",
            aws_region="us-west-2",
            media_url_presign_enabled=True,
            media_url_presign_expires_seconds=3600,
        ),
    )
    monkeypatch.setattr(media_urls, "_s3_client", lambda: mock_client)

    url = (
        "https://abdoun-dev-assets-usw2.s3.us-west-2.amazonaws.com/"
        "agency_legal_document/id/file.pdf"
    )
    result = resolve_readable_media_url(url)

    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "abdoun-dev-assets-usw2", "Key": "agency_legal_document/id/file.pdf"},
        ExpiresIn=3600,
        HttpMethod="GET",
    )
    assert result == mock_client.generate_presigned_url.return_value
    assert "response-content-type" not in result.lower()


def test_generate_presigned_get_url_uses_configured_expiry(monkeypatch) -> None:
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://example.s3.amazonaws.com/key?X-Amz-Signature=x"
    monkeypatch.setattr(
        media_urls,
        "get_settings",
        lambda: _settings(
            aws_s3_bucket="example",
            media_url_presign_enabled=True,
            media_url_presign_expires_seconds=120,
        ),
    )
    monkeypatch.setattr(media_urls, "_s3_client", lambda: mock_client)

    generate_presigned_get_url("agency_legal_document/a/b.pdf")
    kwargs = mock_client.generate_presigned_url.call_args.kwargs
    assert mock_client.generate_presigned_url.call_args.args[0] == "get_object"
    assert kwargs["HttpMethod"] == "GET"
    assert kwargs["ExpiresIn"] == 120


def test_parse_s3_error_xml_extracts_code_and_message() -> None:
    body = """<?xml version="1.0" encoding="UTF-8"?>
<Error>
  <Code>SignatureDoesNotMatch</Code>
  <Message>The request signature we calculated does not match the signature you provided.</Message>
  <StringToSign>AWS4-HMAC-SHA256\\nPOST</StringToSign>
</Error>
"""
    code, message = parse_s3_error_xml(body)
    assert code == "SignatureDoesNotMatch"
    assert message is not None
    assert "does not match" in message


def test_log_s3_error_redacts_credentials(caplog) -> None:
    error = ClientError(
        {
            "Error": {
                "Code": "AccessDenied",
                "Message": "Access Denied X-Amz-Credential=AKIAEXAMPLE/20260820/us-west-2/s3/aws4_request",
            },
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "HeadObject",
    )
    with caplog.at_level("WARNING"):
        media_urls.log_s3_error("head_object", error, object_key="agency_legal_document/id/file.pdf")
    assert "AccessDenied" in caplog.text
    assert "[REDACTED]" in caplog.text
    assert "AKIAEXAMPLE" not in caplog.text
