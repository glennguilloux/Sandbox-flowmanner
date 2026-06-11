#!/usr/bin/env python3
"""
FastAPI Authentication Dependencies
JWT-based authentication for API endpoints
"""

import logging
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer(auto_error=False)


class JWTAuth:
    """JWT authentication dependency for FastAPI"""

    JWT_SECRET_KEY: str = None
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    @classmethod
    def _get_secret(cls) -> str:
        """Get JWT secret key - REQUIRED for security"""
        if cls.JWT_SECRET_KEY is None:
            secret = os.getenv("JWT_SECRET_KEY")
            if not secret:
                raise ValueError("JWT_SECRET_KEY environment variable is required")
            cls.JWT_SECRET_KEY = secret
        return cls.JWT_SECRET_KEY

    @staticmethod
    def verify_token(credentials: HTTPAuthorizationCredentials) -> dict:
        """Verify JWT token and return payload"""
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            token = credentials.credentials
            payload = jwt.decode(token, JWTAuth._get_secret(), algorithms=[JWTAuth.JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    def get_current_user_id(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> int:
        """Get current user ID from JWT token"""
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = JWTAuth.verify_token(credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return int(user_id)

    @staticmethod
    def get_admin_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> int:
        """Require admin authentication"""
        payload = JWTAuth.verify_token(credentials)
        user_id = payload.get("sub")
        is_admin = payload.get("is_admin", False)

        if not user_id or not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return int(user_id)

    @staticmethod
    def get_optional_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> int | None:
        """Get user ID if authenticated, None otherwise (for public endpoints)"""
        if not credentials:
            return None

        try:
            payload = JWTAuth.verify_token(credentials)
            return int(payload.get("sub", 0)) if payload.get("sub") else None
        except HTTPException:
            return None


# Common auth dependencies
get_current_user = JWTAuth.get_current_user_id
get_optional_user = JWTAuth.get_optional_user
require_admin = JWTAuth.get_admin_user


def get_current_active_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> int:
    """
    Get current active user ID from JWT token.

    This is an alias for get_current_user that provides a clear name
    for endpoints requiring an active authenticated user.

    Returns:
        int: The current user's ID

    Raises:
        HTTPException: If not authenticated
    """
    return JWTAuth.get_current_user_id(credentials)
