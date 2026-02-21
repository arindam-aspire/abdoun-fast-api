"""
Centralized HTTP status codes for the application.
All HTTP status codes should be defined here.
"""

from enum import IntEnum


class HTTPStatus(IntEnum):
    """HTTP status codes"""
    # Success
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    
    # Client Errors
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    
    # Server Errors
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


# Common status code references
STATUS_OK = HTTPStatus.OK
STATUS_CREATED = HTTPStatus.CREATED
STATUS_NOT_FOUND = HTTPStatus.NOT_FOUND
STATUS_BAD_REQUEST = HTTPStatus.BAD_REQUEST
STATUS_UNPROCESSABLE_ENTITY = HTTPStatus.UNPROCESSABLE_ENTITY
STATUS_INTERNAL_SERVER_ERROR = HTTPStatus.INTERNAL_SERVER_ERROR
STATUS_FORBIDDEN = HTTPStatus.FORBIDDEN

