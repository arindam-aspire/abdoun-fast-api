"""Helpers to compare mounted route signatures between legacy and refactored apps."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute


def collect_route_signatures(app: FastAPI) -> set[tuple[str, str]]:
    sig: set[tuple[str, str]] = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods or []:
                if method == "HEAD":
                    continue
                sig.add((method.upper(), route.path))
    return sig


def assert_route_parity(legacy_app: FastAPI, refactored_app: FastAPI) -> None:
    assert collect_route_signatures(legacy_app) == collect_route_signatures(refactored_app)
