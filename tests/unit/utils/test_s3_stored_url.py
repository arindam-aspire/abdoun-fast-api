"""Tests for S3 stored URL → object key extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.utils.s3_stored_url import extract_s3_object_key, looks_like_existing_aws_presigned_url


def _settings(*, bucket: str = "abdoun-dev-assets-usw2", region: str = "us-west-2") -> MagicMock:
    s = MagicMock()
    s.aws_s3_bucket = bucket
    s.aws_region = region
    s.aws_s3_public_base_url = None
    s.aws_s3_endpoint_url = None
    return s


def test_extract_virtual_host_style() -> None:
    url = "https://abdoun-dev-assets-usw2.s3.us-west-2.amazonaws.com/users/profile/u1/profile_pic/a.png"
    key = extract_s3_object_key(url, _settings())
    assert key == "users/profile/u1/profile_pic/a.png"


def test_extract_raw_key() -> None:
    assert extract_s3_object_key("users/profile/u1/profile_pic/a.png", _settings()) == "users/profile/u1/profile_pic/a.png"


def test_extract_agency_profile_doc_raw_key() -> None:
    agency_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    key = f"{agency_id}/profile_doc/license.pdf"
    assert extract_s3_object_key(key, _settings()) == key


def test_extract_agency_logo_raw_key() -> None:
    agency_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    key = f"{agency_id}/profile_doc/logo/brand.png"
    assert extract_s3_object_key(key, _settings()) == key


def test_extract_agency_logo_legacy_path() -> None:
    agency_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    key = f"{agency_id}/logo/brand.png"
    assert extract_s3_object_key(key, _settings()) == key


def test_extract_agency_profile_doc_virtual_host() -> None:
    agency_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    url = (
        f"https://abdoun-dev-assets-usw2.s3.us-west-2.amazonaws.com/"
        f"{agency_id}/profile_doc/license.pdf"
    )
    assert extract_s3_object_key(url, _settings()) == f"{agency_id}/profile_doc/license.pdf"


def test_extract_public_base_url_prefix() -> None:
    s = _settings()
    s.aws_s3_public_base_url = "https://cdn.example.com/assets"
    assert (
        extract_s3_object_key("https://cdn.example.com/assets/properties/1/images/x.jpg", s)
        == "properties/1/images/x.jpg"
    )


def test_external_url_returns_none() -> None:
    assert extract_s3_object_key("https://www.youtube.com/watch?v=1", _settings()) is None


def test_presigned_not_reparsed_as_plain() -> None:
    u = "https://bucket.s3.amazonaws.com/key?AWSAccessKeyId=AKIA&Signature=abc&Expires=1"
    assert looks_like_existing_aws_presigned_url(u) is True
    assert extract_s3_object_key(u, _settings(bucket="bucket")) is None
