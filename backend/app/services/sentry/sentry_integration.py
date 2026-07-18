"""
Sentry Integration Service

Provides Sentry SDK initialization, error capture, and integration
with the existing ObservabilityService for unified error tracking.
"""

import logging
import os
import socket
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Optional Sentry SDK support
SENTRY_AVAILABLE = False
sentry_sdk = None
FastApiIntegration = None
RedisIntegration = None
SqlalchemyIntegration = None
CeleryIntegration = None
SamplingContext = None

try:
    import sentry_sdk  # type: ignore[assignment,no-redef]

    SENTRY_AVAILABLE = True
except ImportError:
    logger.warning("sentry-sdk not installed. Sentry integration disabled.")

if SENTRY_AVAILABLE:
    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore[assignment,no-redef]
    except ImportError:
        logger.debug("sentry-sdk FastApiIntegration not available")
    try:
        from sentry_sdk.integrations.redis import RedisIntegration  # type: ignore[assignment,no-redef]
    except ImportError:
        logger.debug("sentry-sdk RedisIntegration not available")
    try:
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration  # type: ignore[assignment,no-redef]
    except ImportError:
        logger.debug("sentry-sdk SqlalchemyIntegration not available")
    try:
        from sentry_sdk.integrations.celery import CeleryIntegration  # type: ignore[assignment,no-redef]
    except ImportError:
        logger.debug("sentry-sdk CeleryIntegration not available")
    try:
        from sentry_sdk.tracing import SamplingContext  # type: ignore[assignment,no-redef]
    except ImportError:
        logger.debug("sentry-sdk SamplingContext not available")


@dataclass
class SentryConfig:
    """Configuration for Sentry integration"""

    dsn: str | None = None
    environment: str = "production"
    release: str | None = None
    traces_sample_rate: float = 1.0
    profiles_sample_rate: float = 0.1
    mcp_enabled: bool = True
    mcp_url: str = "https://mcp.sentry.dev/mcp"
    enable_seer: bool = True
    org_slug: str | None = None
    project_slug: str | None = None

    # Data scrubbing settings
    scrub_pii: bool = True
    scrub_api_keys: bool = True
    sensitive_fields: list = field(
        default_factory=lambda: [
            "password",
            "secret",
            "token",
            "api_key",
            "authorization",
            "credit_card",
            "ssn",
            "email",
            "phone",
        ]
    )

    # Alert settings
    alert_email: str | None = None

    @classmethod
    def from_env(cls) -> "SentryConfig":
        """Load configuration from environment variables"""
        return cls(
            dsn=os.getenv("SENTRY_DSN"),
            environment=os.getenv("SENTRY_ENVIRONMENT", os.getenv("NODE_ENV", "production")),
            release=os.getenv("SENTRY_RELEASE", os.getenv("GIT_COMMIT_SHA")),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            mcp_enabled=os.getenv("SENTRY_MCP_ENABLED", "true").lower() == "true",
            mcp_url=os.getenv("SENTRY_MCP_URL", "https://mcp.sentry.dev/mcp"),
            enable_seer=os.getenv("SENTRY_ENABLE_SEER", "true").lower() == "true",
            org_slug=os.getenv("SENTRY_ORG_SLUG"),
            project_slug=os.getenv("SENTRY_PROJECT_SLUG"),
            scrub_pii=os.getenv("SENTRY_SCRUB_PII", "true").lower() == "true",
            scrub_api_keys=os.getenv("SENTRY_SCRUB_API_KEYS", "true").lower() == "true",
            alert_email=os.getenv("SENTRY_ALERT_EMAIL"),
        )


class SentryIntegration:
    """
    Sentry SDK integration for the workflows platform.

    Features:
    - SDK initialization with FastAPI, Redis, SQLAlchemy integrations
    - Error capture with context enrichment
    - Performance monitoring
    - Integration with ObservabilityService
    - Data scrubbing for sensitive information
    """

    def __init__(self, config: SentryConfig | None = None):
        self.config = config or SentryConfig.from_env()
        self._initialized = False
        self._error_handlers: list[Callable[[dict[str, Any]], Awaitable[None]]] = []

    def initialize(self) -> bool:
        """
        Initialize Sentry SDK with all integrations.

        Returns:
            True if initialized successfully, False otherwise
        """
        if not SENTRY_AVAILABLE:
            logger.warning("Sentry SDK not available, skipping initialization")
            return False

        if not self.config.dsn:
            logger.warning("SENTRY_DSN not configured, Sentry integration disabled")
            return False

        if self._initialized:
            logger.debug("Sentry already initialized")
            return True

        # Validate DNS resolution for the Sentry ingest host.
        # If the container has no outbound DNS (common in Docker networks),
        # fail fast with a single log line instead of letting urllib3 spam
        # retries every cycle.
        try:
            hostname = urlparse(self.config.dsn).hostname
            if hostname:
                socket.getaddrinfo(hostname, 443)
        except socket.gaierror as e:
            logger.warning(
                "Sentry DSN host %s cannot be resolved (%s) — disabling Sentry error tracking",
                hostname,
                e,
            )
            return False

        try:
            # Configure integrations (only include those available in this sentry-sdk version)
            integrations: list[Any] = []
            if FastApiIntegration is not None:
                integrations.append(FastApiIntegration())
            if RedisIntegration is not None:
                integrations.append(RedisIntegration())
            if SqlalchemyIntegration is not None:
                integrations.append(SqlalchemyIntegration())
            if CeleryIntegration is not None:
                integrations.append(CeleryIntegration())

            # Initialize Sentry SDK
            sentry_sdk.init(  # type: ignore[attr-defined]
                dsn=self.config.dsn,
                environment=self.config.environment,
                release=self.config.release,
                traces_sample_rate=self.config.traces_sample_rate,
                profiles_sample_rate=self.config.profiles_sample_rate,
                integrations=integrations,
                # Custom before_send for data scrubbing
                before_send=self._before_send,
                before_send_transaction=self._before_send_transaction,
                # Attach stack traces
                attach_stacktrace=True,
                # Send default PII (controlled by scrub_pii)
                send_default_pii=not self.config.scrub_pii,
                # Server name for identification
                server_name="workflows.glennguilloux.com",
            )

            # Set user context if available
            sentry_sdk.set_tag("platform", "workflows-backend")  # type: ignore[attr-defined]
            sentry_sdk.set_tag("mcp_enabled", self.config.mcp_enabled)  # type: ignore[attr-defined]
            sentry_sdk.set_tag("seer_enabled", self.config.enable_seer)  # type: ignore[attr-defined]

            self._initialized = True
            logger.info("✅ Sentry SDK initialized (environment: %s)", self.config.environment)
            return True

        except Exception as e:
            logger.error("Failed to initialize Sentry SDK: %s", e)
            return False

    def _before_send(self, event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        """
        Process event before sending to Sentry.
        Handles data scrubbing and filtering.
        """
        if not self.config.scrub_pii and not self.config.scrub_api_keys:
            return event

        # Scrub sensitive data from request
        if "request" in event:
            event["request"] = self._scrub_dict(event["request"])

        # Scrub sensitive data from context
        if "contexts" in event:
            event["contexts"] = self._scrub_dict(event["contexts"])

        # Scrub extra data
        if "extra" in event:
            event["extra"] = self._scrub_dict(event["extra"])

        return event

    def _before_send_transaction(self, event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        """Process transaction before sending to Sentry."""
        # Apply same scrubbing to transactions
        return self._before_send(event, hint)

    def _scrub_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively scrub sensitive fields from a dictionary."""
        if not isinstance(data, dict):
            return data

        scrubbed: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Check if this is a sensitive field
            is_sensitive = any(sensitive in key_lower for sensitive in self.config.sensitive_fields)

            if is_sensitive:
                scrubbed[key] = "[Filtered]"
            elif isinstance(value, dict):
                scrubbed[key] = self._scrub_dict(value)
            elif isinstance(value, list):
                scrubbed[key] = [self._scrub_dict(item) if isinstance(item, dict) else item for item in value]
            else:
                scrubbed[key] = value

        return scrubbed

    def capture_exception(
        self,
        error: Exception,
        agent_id: str | None = None,
        workflow_id: str | None = None,
        tool_name: str | None = None,
        context: dict[str, Any] | None = None,
        level: str = "error",
    ) -> str | None:
        """
        Capture an exception and send to Sentry.

        Args:
            error: The exception to capture
            agent_id: Agent where error occurred
            workflow_id: Workflow where error occurred
            tool_name: Tool that caused the error
            context: Additional context
            level: Error level (debug, info, warning, error, fatal)

        Returns:
            Sentry event ID if captured, None otherwise
        """
        if not self._initialized or not SENTRY_AVAILABLE:
            return None

        try:
            # Set context tags
            with sentry_sdk.push_scope() as scope:  # type: ignore[attr-defined]
                if agent_id:
                    scope.set_tag("agent_id", agent_id)
                if workflow_id:
                    scope.set_tag("workflow_id", workflow_id)
                if tool_name:
                    scope.set_tag("tool_name", tool_name)

                scope.set_level(level)

                # Add context
                if context:
                    scope.set_context("error_context", context)

                # Capture the exception
                event_id = sentry_sdk.capture_exception(error)  # type: ignore[attr-defined]

                logger.debug("Captured error in Sentry: %s", event_id)
                return event_id

        except Exception as e:
            logger.error("Failed to capture exception in Sentry: %s", e)
            return None

    def capture_message(self, message: str, level: str = "info", context: dict[str, Any] | None = None) -> str | None:
        """
        Capture a message and send to Sentry.

        Args:
            message: The message to capture
            level: Message level (debug, info, warning, error, fatal)
            context: Additional context

        Returns:
            Sentry event ID if captured, None otherwise
        """
        if not self._initialized or not SENTRY_AVAILABLE:
            return None

        try:
            with sentry_sdk.push_scope() as scope:  # type: ignore[attr-defined]
                scope.set_level(level)
                if context:
                    scope.set_context("message_context", context)
                event_id = sentry_sdk.capture_message(message, level=level)  # type: ignore[attr-defined]
                return event_id
        except Exception as e:
            logger.error("Failed to capture message in Sentry: %s", e)
            return None

    def set_user(self, user_id: str, email: str | None = None, username: str | None = None):
        """Set user context for Sentry events."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return

        sentry_sdk.set_user(  # type: ignore[attr-defined]
            {
                "id": user_id,
                "email": email,
                "username": username,
            }
        )

    def set_context(self, name: str, context: dict[str, Any]):
        """Set additional context for Sentry events."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return

        sentry_sdk.set_context(name, context)  # type: ignore[attr-defined]

    def add_breadcrumb(
        self,
        message: str,
        category: str = "custom",
        level: str = "info",
        data: dict[str, Any] | None = None,
    ):
        """Add a breadcrumb for debugging."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return

        sentry_sdk.add_breadcrumb(  # type: ignore[attr-defined]
            message=message, category=category, level=level, data=data or {}
        )

    def start_transaction(self, name: str, op: str = "function", **kwargs):
        """Start a new Sentry transaction for performance monitoring."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return None

        return sentry_sdk.start_transaction(name=name, op=op, **kwargs)  # type: ignore[attr-defined]

    async def create_error_handler_for_observability(self, error_record: Any) -> None:
        """
        Handler for ObservabilityService error alerts.
        This integrates Sentry with the existing observability system.
        """
        try:
            # Extract error info from ErrorRecord
            error_id = getattr(error_record, "error_id", None)
            error_type = getattr(error_record, "error_type", "Unknown")
            message = getattr(error_record, "message", "Unknown error")
            stack_trace = getattr(error_record, "stack_trace", "")
            agent_id = getattr(error_record, "agent_id", None)
            tool_name = getattr(error_record, "tool_name", None)
            trace_id = getattr(error_record, "trace_id", None)
            context = getattr(error_record, "context", {})

            # Create a synthetic exception for capture
            try:
                raise Exception(f"{error_type}: {message}")
            except Exception as e:
                e.__traceback__ = self._create_traceback(stack_trace) if stack_trace else None

                event_id = self.capture_exception(
                    error=e,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    context={
                        **context,
                        "error_id": error_id,
                        "trace_id": trace_id,
                        "stack_trace": stack_trace,
                    },
                )

                # Store event_id in context for correlation
                if hasattr(error_record, "context") and event_id:
                    error_record.context["sentry_event_id"] = event_id

        except Exception as e:
            logger.error("Error in Sentry error handler: %s", e)

    def _create_traceback(self, stack_trace: str):
        """Create a traceback object from string representation."""
        # This is a simplified version - in production you'd parse the stack trace
        import sys

        try:
            # Parse stack trace and create proper traceback
            return sys.exc_info()[2]
        except Exception:
            logger.debug("Failed to create traceback from stack trace string")
            return None

    def is_initialized(self) -> bool:
        """Check if Sentry is initialized."""
        return self._initialized

    def flush(self, timeout: float = 2.0):
        """Flush pending Sentry events."""
        if self._initialized and SENTRY_AVAILABLE:
            sentry_sdk.flush(timeout=timeout)  # type: ignore[attr-defined]


# Singleton instance
_sentry_integration: SentryIntegration | None = None


def get_sentry_integration() -> SentryIntegration:
    """Get or create the Sentry integration singleton."""
    global _sentry_integration
    if _sentry_integration is None:
        _sentry_integration = SentryIntegration()
    return _sentry_integration


def init_sentry() -> bool:
    """Initialize Sentry integration. Call at app startup."""
    integration = get_sentry_integration()
    return integration.initialize()
