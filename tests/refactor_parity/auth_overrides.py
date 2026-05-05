"""Shared auth overrides for parity tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FakeCurrentUser:
    id: int = 1
    email: str = "parity@example.com"
    role: str = "admin"
    is_active: bool = True
    cognito_sub: str = "parity-sub"
    permissions: list[str] = field(default_factory=list)

    def dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "cognito_sub": self.cognito_sub,
            "permissions": self.permissions,
        }


def fake_current_user_sync() -> FakeCurrentUser:
    return FakeCurrentUser()


async def fake_current_user_async() -> FakeCurrentUser:
    return FakeCurrentUser()

