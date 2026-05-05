"""Parity client utilities for legacy/refactored route comparison."""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.main import app as legacy_app


class WriteMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    AUTH_REQUIRED_READ = "AUTH_REQUIRED_READ"
    WRITE_WITH_ROLLBACK = "WRITE_WITH_ROLLBACK"
    WRITE_SHAPE_ONLY = "WRITE_SHAPE_ONLY"


class ParityClient:
    def __init__(self, legacy_client: TestClient, refactored_client: TestClient) -> None:
        self.legacy_client = legacy_client
        self.refactored_client = refactored_client

    def request(self, method: str, path: str, **kwargs: Any) -> tuple[Any, Any]:
        legacy_response = self.legacy_client.request(method, path, **kwargs)
        refactored_response = self.refactored_client.request(method, path, **kwargs)
        return legacy_response, refactored_response


def build_legacy_client() -> TestClient:
    return TestClient(legacy_app)


def build_refactored_client(router: APIRouter) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)

