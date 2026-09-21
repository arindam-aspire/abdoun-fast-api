from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailSendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None
    purpose: str | None = None

    def __bool__(self) -> bool:
        return self.success
