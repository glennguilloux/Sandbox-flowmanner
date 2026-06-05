"""
Data Governance Middleware

Middleware for adding data governance features to requests:
- PII detection in request/response data
- Audit logging for sensitive operations
- Data retention policy checks
"""

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..models.audit_log import AuditAction
from ..services.audit_service import AuditService
from ..services.data_governance_metrics import AuditLogMetrics, data_governance_metrics
from ..services.data_masker import DataMasker
from ..services.pii_detector import PIIDetector
from ..services.retention_service import RetentionService


class DataGovernanceMiddleware(BaseHTTPMiddleware):
    """Middleware for data governance features"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.pii_detector = PIIDetector()
        self.data_masker = DataMasker()
        self.audit_service = AuditService()
        self.retention_service = RetentionService()

        # Define sensitive endpoints that require audit logging
        self.sensitive_endpoints = {
            "/api/auth/register": AuditAction.CREATE,
            "/api/auth/login": AuditAction.READ,
            "/api/auth/logout": AuditAction.READ,
            "/api/auth/refresh": AuditAction.READ,
            "/api/auth/me": AuditAction.READ,
            "/api/auth/change-password": AuditAction.UPDATE,
            "/api/auth/delete-account": AuditAction.DELETE,
            "/api/workflows": AuditAction.CREATE,
            "/api/workflows/{workflow_id}": AuditAction.UPDATE,
            "/api/workflows/{workflow_id}": AuditAction.DELETE,
            "/api/n8n/webhook": AuditAction.CREATE,
            "/api/external/workflows": AuditAction.READ,
            "/api/external/workflows/{workflow_id}": AuditAction.READ,
            "/api/external/workflows/{workflow_id}/execute": AuditAction.EXECUTE,
        }

        # Define endpoints that may contain PII
        self.pii_sensitive_endpoints = [
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/change-password",
            "/api/auth/delete-account",
            "/api/workflows",  # Workflows may contain user data
            "/api/n8n/webhook",  # Webhooks may contain user data
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with data governance features"""
        start_time = time.time()

        # Extract user info from request (simplified - in real app, get from JWT)
        user_id = self._extract_user_id(request)
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Check if endpoint requires audit logging
        audit_action = self._get_audit_action(request)

        # Process request
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Log audit event if required
        if audit_action:
            try:
                # Extract resource info from request
                resource_type, resource_id = self._extract_resource_info(request)

                # Log to audit service
                self.audit_service.log_action(
                    action=audit_action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    user_id=user_id or "anonymous",
                    details={
                        "method": request.method,
                        "path": str(request.url.path),
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "ip_address": ip_address,
                    },
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

                # Record metrics
                metrics = AuditLogMetrics(
                    action=audit_action.value,
                    resource_type=resource_type,
                    user_id=int(user_id) if user_id and user_id.isdigit() else None,
                    duration_ms=duration_ms,
                    success=response.status_code < 400,
                )
                data_governance_metrics.record_audit_event(metrics)

            except Exception as e:
                # Don't fail the request if audit logging fails
                print(f"Audit logging failed: {e}")

        return response

    def _extract_user_id(self, request: Request) -> str | None:
        """Extract user ID from request (simplified)"""
        # In a real app, this would extract from JWT token
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # Simplified - just return a placeholder
            return "user_123"
        return None

    def _get_audit_action(self, request: Request) -> AuditAction | None:
        """Get audit action for request path and method"""
        path = str(request.url.path)
        method = request.method

        # Map HTTP methods to audit actions
        method_to_action = {
            "GET": AuditAction.READ,
            "POST": AuditAction.CREATE,
            "PUT": AuditAction.UPDATE,
            "PATCH": AuditAction.UPDATE,
            "DELETE": AuditAction.DELETE,
        }

        # Check if endpoint is in sensitive list
        for endpoint_pattern, action in self.sensitive_endpoints.items():
            if self._path_matches_pattern(path, endpoint_pattern):
                return action

        # Fallback to method-based action
        return method_to_action.get(method)

    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern with path parameters"""
        if pattern == path:
            return True

        # Simple pattern matching (in real app, use proper routing)
        pattern_parts = pattern.split("/")
        path_parts = path.split("/")

        if len(pattern_parts) != len(path_parts):
            return False

        for pattern_part, path_part in zip(pattern_parts, path_parts, strict=False):
            if pattern_part.startswith("{") and pattern_part.endswith("}"):
                continue  # Path parameter matches anything
            if pattern_part != path_part:
                return False

        return True

    def _extract_resource_info(self, request: Request) -> tuple[str, str]:
        """Extract resource type and ID from request"""
        path = str(request.url.path)

        # Map paths to resource types
        if path.startswith("/api/auth/"):
            return "auth", "user"
        elif path.startswith("/api/workflows"):
            # Extract workflow ID if present
            parts = path.split("/")
            if len(parts) > 3 and parts[3].isdigit():
                return "workflow", parts[3]
            return "workflow", "collection"
        elif path.startswith("/api/n8n/"):
            return "n8n_webhook", "webhook"
        elif path.startswith("/api/external/workflows"):
            parts = path.split("/")
            if len(parts) > 4 and parts[4]:
                return "external_workflow", parts[4]
            return "external_workflow", "collection"

        return "unknown", "unknown"


def add_data_governance_middleware(app: ASGIApp) -> ASGIApp:
    """Add data governance middleware to FastAPI app"""
    return DataGovernanceMiddleware(app)
