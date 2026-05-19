"""Exceptions for the property image multipart upload endpoint."""

from __future__ import annotations


class PropertyImageUploadError(Exception):
    """Raised when property image upload validation or processing fails."""

    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.detail = detail
        super().__init__(message)
