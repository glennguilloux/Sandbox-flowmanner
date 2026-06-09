"""
LangGraph Authentication Module

JWT authentication and user context management for LangGraph agent system.
Provides authentication decorators, user context extraction, and permission checking.
"""

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

import jwt
from flask import g, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

logger = logging.getLogger(__name__)


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
        """
        Check if user has specific permission.

        Args:
            permission: Permission string to check

        Returns:
            True if user has permission, False otherwise
        """
        # Admin users have all permissions
        if self.is_admin:
            return True

        # Check specific permission
        return self.permissions.get(permission, False)

    def can_access_tool(self, tool_id: str) -> bool:
        """
        Check if user can access specific tool.

        Args:
            tool_id: Tool identifier

        Returns:
            True if user can access tool, False otherwise
        """
        # Admin users can access all tools
        if self.is_admin:
            return True

        # Check tool-specific permission
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
        """
        Create UserContext from JWT payload.

        Args:
            jwt_payload: JWT payload dictionary

        Returns:
            UserContext instance
        """
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


def auth_required(f: Callable) -> Callable:
    """
    Decorator for requiring JWT authentication.

    Args:
        f: Function to decorate

    Returns:
        Decorated function
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Verify JWT token
            verify_jwt_in_request()

            # Get JWT identity and payload
            user_id = get_jwt_identity()
            jwt_payload = get_jwt()

            if not user_id:
                return (
                    jsonify(
                        {
                            "error": "Unauthorized",
                            "message": "Invalid token",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ),
                    401,
                )

            # Create user context
            user_context = UserContext.from_jwt(jwt_payload)

            # Store user context in Flask's g object
            g.user_context = user_context

            logger.info(
                "Authenticated user: %s (ID: %s)",
                user_context.username,
                user_context.user_id,
            )

            return f(*args, **kwargs)

        except Exception as e:
            logger.error("Authentication error: %s", e)
            return (
                jsonify(
                    {
                        "error": "Unauthorized",
                        "message": "Authentication failed",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ),
                401,
            )

    return decorated_function


def admin_required(f: Callable) -> Callable:
    """
    Decorator for requiring admin privileges.

    Args:
        f: Function to decorate

    Returns:
        Decorated function
    """

    @wraps(f)
    @auth_required
    def decorated_function(*args, **kwargs):
        user_context = getattr(g, "user_context", None)

        if not user_context or not user_context.is_admin:
            return (
                jsonify(
                    {
                        "error": "Forbidden",
                        "message": "Admin privileges required",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ),
                403,
            )

        return f(*args, **kwargs)

    return decorated_function


def permission_required(permission: str) -> Callable:
    """
    Decorator factory for requiring specific permission.

    Args:
        permission: Permission string required

    Returns:
        Decorator function
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        @auth_required
        def decorated_function(*args, **kwargs):
            user_context = getattr(g, "user_context", None)

            if not user_context or not user_context.has_permission(permission):
                return (
                    jsonify(
                        {
                            "error": "Forbidden",
                            "message": f"Permission '{permission}' required",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ),
                    403,
                )

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def tool_access_required(tool_id: str) -> Callable:
    """
    Decorator factory for requiring tool access permission.

    Args:
        tool_id: Tool identifier

    Returns:
        Decorator function
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        @auth_required
        def decorated_function(*args, **kwargs):
            user_context = getattr(g, "user_context", None)

            if not user_context or not user_context.can_access_tool(tool_id):
                return (
                    jsonify(
                        {
                            "error": "Forbidden",
                            "message": f"Access to tool '{tool_id}' not allowed",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ),
                    403,
                )

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_current_user() -> UserContext | None:
    """
    Get current user context from request.

    Returns:
        UserContext instance or None if not authenticated
    """
    return getattr(g, "user_context", None)


def get_current_user_id() -> int | None:
    """
    Get current user ID from request.

    Returns:
        User ID or None if not authenticated
    """
    user_context = get_current_user()
    return user_context.user_id if user_context else None


def extract_user_context_from_request() -> UserContext | None:
    """
    Extract user context from request headers.
    Used for background tasks or async operations.

    Returns:
        UserContext instance or None if not authenticated
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Decode JWT token
        secret_key = os.getenv("JWT_SECRET_KEY", "fallback-secret-key")
        algorithm = os.getenv("JWT_ALGORITHM", "HS256")

        payload = jwt.decode(
            token, secret_key, algorithms=[algorithm], options={"verify_exp": True}
        )

        return UserContext.from_jwt(payload)

    except Exception as e:
        logger.debug("Failed to extract user context: %s", e)
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
            # Add user-specific configuration paths
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
