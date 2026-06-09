"""Pydantic validation for recent view upsert request."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.recent_view import RecentViewUpsertRequest


def test_recent_view_requires_property_identifier() -> None:
    with pytest.raises(ValidationError) as exc:
        RecentViewUpsertRequest()
    assert "property_id" in str(exc.value).lower() or "property_hash_id" in str(exc.value).lower()


def test_recent_view_accepts_property_id() -> None:
    pid = uuid.uuid4()
    body = RecentViewUpsertRequest(property_id=pid)
    assert body.property_id == pid
    assert body.property_hash_id is None


def test_recent_view_accepts_property_hash_id() -> None:
    body = RecentViewUpsertRequest(property_hash_id=123456789)
    assert body.property_hash_id == 123456789
    assert body.property_id is None


def test_recent_view_accepts_property_hash_id_camel_case_alias() -> None:
    body = RecentViewUpsertRequest.model_validate({"propertyHashId": 987654321})
    assert body.property_hash_id == 987654321


def test_recent_view_accepts_both_identifiers() -> None:
    pid = uuid.uuid4()
    body = RecentViewUpsertRequest(property_id=pid, property_hash_id=111)
    assert body.property_id == pid
    assert body.property_hash_id == 111


def test_recent_view_accepts_property_id_camel_case_alias() -> None:
    pid = uuid.uuid4()
    body = RecentViewUpsertRequest.model_validate({"propertyId": str(pid)})
    assert body.property_id == pid
