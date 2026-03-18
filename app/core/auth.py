"""
Cognito JWT authentication dependency for FastAPI.

This module provides get_current_user() which:
1. Validates the Authorization Bearer token against Cognito
2. Extracts the 'sub' claim from the JWT
3. Loads the corresponding user from the database
4. Ensures the user is active
"""
import anyio

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.services.cognito import cognito_service
from app.models.user import User
from app.utils.constants import ErrorMessages
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.logger import api_logger

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """FastAPI dependency that validates Cognito JWT and returns the current user.

    Flow: extract Bearer token → verify with Cognito → validate token_use "access"
    → resolve user by cognito_sub (or email fallback) → ensure user is active.

    Args:
        credentials: Injected by HTTPBearer; holds the Bearer token.
        db: Injected database session for user lookup.

    Returns:
        The authenticated, active User model instance.

    Raises:
        HTTPException: 401 if token invalid/missing or user not found; 403 if user inactive.
    """
    # Keep as async FastAPI dependency; allows awaiting if future IO is added.
    await anyio.lowlevel.checkpoint()
    token = credentials.credentials

    # Verify token against Cognito
    payload = cognito_service.verify_token(token)

    if not payload:
        api_logger.warning(format_log_message(LogMessages.Auth.TOKEN_VERIFICATION_FAILED_DEP))
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=ErrorMessages.INVALID_TOKEN,
        )

    # Validate token_use == "access" (as per spec requirement)
    token_use = payload.get("token_use")
    if token_use != "access":
        api_logger.warning(
            format_log_message(
                LogMessages.Auth.TOKEN_VERIFICATION_FAILED,
                error=format_log_message(
                    ErrorMessages.INVALID_TOKEN_USE,
                    token_use=token_use,
                ),
            )
        )
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=ErrorMessages.INVALID_TOKEN,
        )

    # Extract 'sub' claim
    cognito_sub = payload.get("sub")
    if not cognito_sub:
        api_logger.warning(format_log_message(LogMessages.Auth.TOKEN_PAYLOAD_MISSING_SUB))
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=ErrorMessages.MISSING_SUB,
        )

    def _get_user_by(statement):
        return db.execute(statement).scalar_one_or_none()

    # Load user from database by cognito_sub
    user = _get_user_by(select(User).where(User.cognito_sub == cognito_sub))

    # Fallback: if user not found by cognito_sub, try to find by email.
    if not user:
        email = payload.get("email")
        if not email:
            # Try to get email from Cognito by sub
            attrs = cognito_service.get_user_attributes_by_sub(cognito_sub)
            if attrs:
                email = attrs.get("email")

        if email:
            user = _get_user_by(select(User).where(User.email == email))

    if not user:
        api_logger.warning(format_log_message(LogMessages.Auth.USER_NOT_FOUND_SUB, sub=cognito_sub))
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=ErrorMessages.USER_NOT_FOUND,
        )

    # NOTE: This dependency must remain read-only. Any user-sync writes (e.g. cognito_sub,
    # email_verified, phone_verified) should be performed in explicit service flows (login/signup)
    # rather than during request authentication.

    # Ensure user is active
    if not user.is_active:
        api_logger.warning(format_log_message(LogMessages.Auth.INACTIVE_USER_ATTEMPT, email=user.email))
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=ErrorMessages.USER_INACTIVE,
        )

    return user

