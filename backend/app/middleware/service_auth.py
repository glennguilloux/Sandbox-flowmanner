import logging
from functools import wraps
from typing import Any

import jwt
from flask import current_app, jsonify, request

logger = logging.getLogger(__name__)


class ServiceAuthManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def generate_token(
        self, service_name: str, allowed_endpoints: list[str], expires_hours: int = 24
    ) -> str:
        """Generate JWT token for service authentication"""
        payload = {
            "service": service_name,
            "endpoints": allowed_endpoints,
            "exp": jwt.utils.get_int_from_datetime(
                jwt.utils.datetime_from_timestamp(
                    jwt.utils.time.time() + expires_hours * 3600
                )
            ),
            "iat": jwt.utils.time.time(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate JWT token and return payload if valid"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Service token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning('Invalid service token: %s', e)
            return None

    def is_service_allowed(
        self, service_name: str, endpoint: str, allowed_endpoints: list[str]
    ) -> bool:
        """Check if service is allowed to access endpoint"""
        # Check exact match
        if endpoint in allowed_endpoints:
            return True

        # Check wildcard patterns
        for pattern in allowed_endpoints:
            if "*" in pattern:
                # Convert pattern to regex-like matching
                pattern_parts = pattern.split("*")
                if len(pattern_parts) == 2:
                    if endpoint.startswith(pattern_parts[0]) and endpoint.endswith(
                        pattern_parts[1]
                    ):
                        return True

        return False


def require_service_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip authentication if mTLS is disabled
        if not current_app.config.get("MTLS_ENABLED", False):
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning('No authorization header for request to: %s', request.path)
            return (
                jsonify(
                    {
                        "error": "No authorization header",
                        "message": "Service authentication required",
                    }
                ),
                401,
            )

        try:
            # Extract token from "Bearer <token>" format
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Invalid authorization format"}), 401

            token = auth_header.split(" ")[1]

            # Get secret from config
            secret_key = current_app.config.get("SERVICE_JWT_SECRET")
            if not secret_key:
                logger.error("SERVICE_JWT_SECRET not configured")
                return jsonify({"error": "Server configuration error"}), 500

            # Validate token
            auth_manager = ServiceAuthManager(secret_key)
            payload = auth_manager.validate_token(token)

            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            # Check if service is allowed to access this endpoint
            service_name = payload.get("service")
            allowed_endpoints = payload.get("endpoints", [])

            if not auth_manager.is_service_allowed(
                service_name, request.path, allowed_endpoints
            ):
                logger.warning('Service %s not authorized for %s', service_name, request.path)
                return (
                    jsonify(
                        {
                            "error": "Service not authorized",
                            "message": f"Service {service_name} cannot access {request.path}",
                        }
                    ),
                    403,
                )

            # Store service context in request for later use
            request.service_context = {
                "service": service_name,
                "endpoints": allowed_endpoints,
            }

            logger.info('Service %s authenticated for %s', service_name, request.path)
            return f(*args, **kwargs)

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        except Exception as e:
            logger.error('Service authentication error: %s', e)
            return jsonify({"error": "Authentication failed"}), 500

    return decorated


def get_service_context() -> dict[str, Any] | None:
    """Get service context from request"""
    return getattr(request, "service_context", None)


def require_mtls_and_service_auth(f):
    """Combined decorator requiring both mTLS and service authentication"""

    @wraps(f)
    def decorated(*args, **kwargs):
        # First check mTLS
        from .mtls_middleware import require_mtls

        mtls_decorated = require_mtls(f)

        # Then check service auth
        return require_service_auth(mtls_decorated)(*args, **kwargs)

    return decorated


class ServiceRegistry:
    """Registry for service permissions and capabilities"""

    def __init__(self):
        self.services = {}

    def register_service(
        self, name: str, description: str, allowed_endpoints: list[str]
    ):
        """Register a service with its permissions"""
        self.services[name] = {
            "description": description,
            "allowed_endpoints": allowed_endpoints,
            "created_at": jwt.utils.time.time(),
        }

    def get_service_permissions(self, name: str) -> dict[str, Any] | None:
        """Get permissions for a service"""
        return self.services.get(name)

    def list_services(self) -> list[str]:
        """List all registered services"""
        return list(self.services.keys())


# Default service registry
service_registry = ServiceRegistry()

# Register default services
service_registry.register_service(
    name="backend",
    description="Main backend service",
    allowed_endpoints=["/api/*", "/health", "/metrics"],
)

service_registry.register_service(
    name="celery-worker",
    description="Celery worker service",
    allowed_endpoints=["/api/tasks/*", "/api/workers/*"],
)

service_registry.register_service(
    name="celery-beat",
    description="Celery beat scheduler",
    allowed_endpoints=["/api/schedules/*"],
)

service_registry.register_service(
    name="n8n",
    description="n8n workflow automation",
    allowed_endpoints=["/api/webhooks/*", "/api/workflows/*"],
)
