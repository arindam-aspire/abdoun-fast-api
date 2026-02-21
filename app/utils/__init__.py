"""
Utility modules for the application.
"""

from app.utils.constants import (
    ErrorMessages,
    SuccessMessages,
    InfoMessages,
    WarningMessages,
    Defaults,
    GeocodingConstants,
    CSVImportMessages,
    SystemMessages,
)
from app.utils.status_codes import HTTPStatus, STATUS_OK, STATUS_CREATED, STATUS_NOT_FOUND
from app.utils.responses import (
    StandardResponse,
    ErrorResponse,
    SuccessResponse,
    PaginatedResponse,
    ImportResponse,
    create_error_response,
    create_success_response,
)
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import (
    get_logger,
    get_coordinate_update_logger,
    get_emoji_safe_text,
    setup_windows_console_encoding,
    get_coord_logger,
    api_logger,
    service_logger,
    db_logger,
)
from app.utils.security import (
    validate_input_length,
    MAX_INPUT_LENGTH,
    MAX_CURRENCY_INPUT_LENGTH,
    MAX_AREA_INPUT_LENGTH,
    MAX_LOCATION_INPUT_LENGTH,
)

__all__ = [
    # Constants
    "ErrorMessages",
    "SuccessMessages",
    "InfoMessages",
    "WarningMessages",
    "Defaults",
    "GeocodingConstants",
    "CSVImportMessages",
    "SystemMessages",
    # Status Codes
    "HTTPStatus",
    "STATUS_OK",
    "STATUS_CREATED",
    "STATUS_NOT_FOUND",
    # Responses
    "StandardResponse",
    "ErrorResponse",
    "SuccessResponse",
    "PaginatedResponse",
    "ImportResponse",
    "create_error_response",
    "create_success_response",
    # Log Messages
    "LogMessages",
    "format_log_message",
    # Logger
    "get_logger",
    "get_coordinate_update_logger",
    "get_emoji_safe_text",
    "setup_windows_console_encoding",
    "get_coord_logger",
    "api_logger",
    "service_logger",
    "db_logger",
    # Security
    "validate_input_length",
    "MAX_INPUT_LENGTH",
    "MAX_CURRENCY_INPUT_LENGTH",
    "MAX_AREA_INPUT_LENGTH",
    "MAX_LOCATION_INPUT_LENGTH",
]

