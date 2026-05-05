"""Simple result wrappers for domain operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(slots=True)
class Ok(Generic[T]):
    value: T


@dataclass(slots=True)
class Err(Generic[E]):
    error: E

