"""Auth context protocol for refactored domain services."""

from dataclasses import dataclass


@dataclass(slots=True)
class AuthContext:
    user_id: str | None = None
    roles: tuple[str, ...] = ()

