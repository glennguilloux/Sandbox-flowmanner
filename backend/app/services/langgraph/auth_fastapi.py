"""
LangGraph Authentication Module - FastAPI

JWT authentication and user context management for LangGraph agent system.
Provides authentication utilities compatible with FastAPI dependency injection.
"""

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class UserContext:
    """
    User context for request processing.

    Contains user information and permissions for tool execution.
    """

    def __init__(
        self,
        user_id: int,
        username: str,
        email: str,
        is_admin: bool = False,
        permissions: dict[str, bool] = None,
    ):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.is_admin = is_admin
        self.permissions = permissions or {}
        self.created_at = datetime.now(UTC)

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission."""
        if self.is_admin:
            return True
        return self.permissions.get(permission, False)

    def can_access_tool(self, tool_id: str) -> bool:
        """Check if user can access specific tool."""
        if self.is_admin:
            return True
        tool_permission = f"tool.{tool_id}"
        return self.has_permission(tool_permission)

    def to_dict(self) -> dict[str, Any]:
        """Convert user context to dictionary"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "is_admin": self.is_admin,
            "permissions": self.permissions,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_jwt(cls, jwt_payload: dict[str, Any]) -> "UserContext":
        """Create UserContext from JWT payload."""
        user_id = int(jwt_payload.get("sub", 0))
        username = jwt_payload.get("username", "")
        email = jwt_payload.get("email", "")
        is_admin = jwt_payload.get("is_admin", False)
        permissions = jwt_payload.get("permissions", {})

        return cls(
            user_id=user_id,
            username=username,
            email=email,
            is_admin=is_admin,
            permissions=permissions,
        )


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify and decode JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        secret_key = os.getenv("JWT_SECRET_KEY")
        if not secret_key:
            raise ValueError("JWT_SECRET_KEY environment variable is required")

        algorithm = os.getenv("JWT_ALGORITHM", "HS256")

        payload = jwt.decode(
            token, secret_key, algorithms=[algorithm], options={"verify_exp": True}
        )

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.error("Invalid token: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext:
    """
    FastAPI dependency to get current user context from JWT token.

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        UserContext instance

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authorization token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_token(credentials.credentials)
        user_context = UserContext.from_jwt(payload)
        logger.info(
            "Authenticated user: %s (ID: %s)",
            user_context.username,
            user_context.user_id,
        )
        return user_context
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext | None:
    """
    FastAPI dependency to optionally get user context.

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        UserContext instance or None
    """
    if not credentials:
        return None

    try:
        payload = verify_token(credentials.credentials)
        return UserContext.from_jwt(payload)
    except Exception:
        return None


async def require_admin(
    user_context: UserContext = Depends(get_current_user_context),
) -> UserContext:
    """
    FastAPI dependency to require admin privileges.

    Args:
        user_context: User context from get_current_user_context

    Returns:
        UserContext if admin

    Raises:
        HTTPException: If user is not admin
    """
    if not user_context.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user_context


def require_permission(permission: str):
    """
    Factory for creating permission dependency.

    Args:
        permission: Required permission string

    Returns:
        Dependency function
    """

    async def check_permission(
        user_context: UserContext = Depends(get_current_user_context),
    ) -> UserContext:
        if not user_context.has_permission(permission):
            raise HTTPException(
                status_code=403, detail=f"Permission '{permission}' required"
            )
        return user_context

    return check_permission


def require_tool_access(tool_id: str):
    """
    Factory for creating tool access dependency.

    Args:
        tool_id: Tool identifier

    Returns:
        Dependency function
    """

    async def check_tool_access(
        user_context: UserContext = Depends(get_current_user_context),
    ) -> UserContext:
        if not user_context.can_access_tool(tool_id):
            raise HTTPException(
                status_code=403, detail=f"Access to tool '{tool_id}' not allowed"
            )
        return user_context

    return check_tool_access


def extract_user_context_from_request(request: Request) -> UserContext | None:
    """
    Extract user context from FastAPI request headers.

    Args:
        request: FastAPI Request object

    Returns:
        UserContext instance or None
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix
        payload = verify_token(token)
        return UserContext.from_jwt(payload)

    except Exception as e:
        logger.debug("Failed to extract user context: %s", e)
        return None


# Backward compatibility decorators (for non-FastAPI code)
def auth_required(f: Callable) -> Callable:
    """
    Decorator for requiring JWT authentication (backward compatibility).

    Note: For FastAPI routes, use get_current_user_context dependency instead.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.warning(
            "auth_required decorator is deprecated. Use FastAPI dependencies."
        )
        # This is a stub - the actual auth should be done via FastAPI dependencies
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f: Callable) -> Callable:
    """
    Decorator for requiring admin privileges (backward compatibility).

    Note: For FastAPI routes, use require_admin dependency instead.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.warning(
            "admin_required decorator is deprecated. Use FastAPI dependencies."
        )
        return f(*args, **kwargs)

    return decorated_function


def get_current_user() -> UserContext | None:
    """
    Get current user context - deprecated, use dependency injection instead.

    Returns:
        UserContext or None
    """
    logger.warning("get_current_user() is deprecated. Use FastAPI dependencies.")
    return None


def get_current_user_id() -> int | None:
    """
    Get current user ID - deprecated, use dependency injection instead.

    Returns:
        User ID or None
    """
    logger.warning("get_current_user_id() is deprecated. Use FastAPI dependencies.")
    return None


class UserIsolationManager:
    """
    Manages user isolation for configurations and data.

    Ensures users can only access their own data and configurations.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.UserIsolationManager")

    def filter_by_user(self, query, model_class, user_context: UserContext):
        """
        Filter query to only include user's data.

        Args:
            query: SQLAlchemy query object
            model_class: Model class to check for user_id field
            user_context: User context

        Returns:
            Filtered query
        """
        if not user_context:
            raise ValueError("User context required for filtering")

        # Check if model has user_id field
        if hasattr(model_class, "user_id"):
            return query.filter(model_class.user_id == user_context.user_id)

        # Check if model has created_by field
        elif hasattr(model_class, "created_by"):
            return query.filter(model_class.created_by == user_context.user_id)

        # Model doesn't support user isolation
        self.logger.warning(
            f"Model {model_class.__name__} doesn't support user isolation"
        )
        return query

    def validate_user_access(
        self, item, user_context: UserContext, field_name: str = "user_id"
    ) -> bool:
        """
        Validate that user can access specific item.

        Args:
            item: Database model instance
            user_context: User context
            field_name: Field name to check for user ID

        Returns:
            True if user can access item, False otherwise
        """
        if not user_context:
            return False

        # Admin users can access everything
        if user_context.is_admin:
            return True

        # Check if item has the specified field
        if hasattr(item, field_name):
            item_user_id = getattr(item, field_name)
            return item_user_id == user_context.user_id

        # Item doesn't support user isolation
        self.logger.warning(
            f"Item of type {type(item).__name__} doesn't support user isolation"
        )
        return False

    def create_user_context_for_tool(self, user_context: UserContext) -> dict[str, Any]:
        """
        Create context dictionary for tool execution with user isolation.

        Args:
            user_context: User context

        Returns:
            Context dictionary for tool execution
        """
        if not user_context:
            return {}

        return {
            "user_id": user_context.user_id,
            "username": user_context.username,
            "is_admin": user_context.is_admin,
            "permissions": user_context.permissions,
            "user_config_dir": f"/config/users/{user_context.user_id}",
            "user_data_dir": f"/data/users/{user_context.user_id}",
            "user_cache_dir": f"/cache/users/{user_context.user_id}",
        }


# Global instance
_user_isolation_manager = None


def get_user_isolation_manager() -> UserIsolationManager:
    """Get global user isolation manager instance"""
    global _user_isolation_manager
    if _user_isolation_manager is None:
        _user_isolation_manager = UserIsolationManager()
    return _user_isolation_manager
