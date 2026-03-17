"""
Standard response formats for the API.
All API response structures should be defined here.
"""

from typing import Any, List, TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar('T')


class StandardResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response format"""
    success: bool = False
    error: str
    detail: Optional[str] = None
    status_code: Optional[int] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response format"""
    items: List[T]
    total: int
    limit: Optional[int] = None
    offset: Optional[int] = None


class ImportResponse(BaseModel):
    """Response format for CSV import operations"""
    created: int
    updated: Optional[int] = None
    skipped: Optional[int] = None


def create_error_response(
    error: str,
    detail: Optional[str] = None,
    status_code: Optional[int] = None
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
    message: Optional[str] = None
) -> StandardResponse:
    """Helper function to create standardized success responses"""
    return StandardResponse(
        success=True,
        data=data,
        message=message
    )

