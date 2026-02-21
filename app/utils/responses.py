"""
Standard response formats for the API.
All API response structures should be defined here.
"""

from typing import Any, TypeVar
from pydantic import BaseModel

T = TypeVar('T')


class StandardResponse[T](BaseModel):
    """Standard API response wrapper"""
    success: bool = True
    data: T | None = None
    message: str | None = None
    error: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response format"""
    success: bool = False
    error: str
    detail: str | None = None
    status_code: int | None = None


class SuccessResponse[T](BaseModel):
    """Standard success response format"""
    success: bool = True
    data: T
    message: str | None = None


class PaginatedResponse[T](BaseModel):
    """Standard paginated response format"""
    items: list[T]
    total: int
    limit: int | None = None
    offset: int | None = None


class ImportResponse(BaseModel):
    """Response format for CSV import operations"""
    created: int
    updated: int | None = None
    skipped: int | None = None


def create_error_response(
    error: str,
    detail: str | None = None,
    status_code: int | None = None
) -> ErrorResponse:
    """Helper function to create standardized error responses"""
    return ErrorResponse(
        success=False,
        error=error,
        detail=detail,
        status_code=status_code
    )


def create_success_response(
    data: Any,
    message: str | None = None
) -> SuccessResponse:
    """Helper function to create standardized success responses"""
    return SuccessResponse(
        success=True,
        data=data,
        message=message
    )

