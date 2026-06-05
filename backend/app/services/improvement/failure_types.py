"""
Failure Types Module - Phase 1: Foundation Layer

This module provides the structured taxonomy for failure classification,
separating infrastructure failures (handled by self_healing.py) from
application/agentic failures (handled by improvement_loop_v2.py).

Part of the Autonomous Self-Improvement Architecture.
"""

import asyncio
import json
import logging
import re
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Optional Sentry integration
try:
    import sentry_sdk

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    sentry_sdk = None


class FailureType(Enum):
    """
    Structured taxonomy separating infrastructure vs. application failures.

    Infrastructure failures are handled by self_healing.py
    Application/Agentic failures are handled by improvement_loop_v2.py
    """

    # ============================================
    # INFRASTRUCTURE FAILURES (→ self_healing.py)
    # ============================================

    # External API errors - can't be fixed by self-improvement immediately
    TOOL_API_ERROR = "tool_api_error"

    # Tool execution timeout
    TOOL_TIMEOUT = "tool_timeout"

    # Resource exhaustion (memory, CPU, GPU)
    RESOURCE_EXHAUSTION = "resource_exhaustion"

    # Network/connection failures
    CONNECTION_FAILURE = "connection_failure"

    # Rate limiting (429 errors)
    RATE_LIMITED = "rate_limited"

    # Service unavailable (503 errors)
    SERVICE_UNAVAILABLE = "service_unavailable"

    # ============================================
    # APPLICATION/AGENTIC FAILURES (→ improvement_loop_v2.py)
    # ============================================

    # Tool received invalid input parameters
    TOOL_INVALID_INPUT = "tool_invalid_input"

    # Tool returned unexpected/malformed output
    TOOL_INVALID_OUTPUT = "tool_invalid_output"

    # LLM generated non-existent or hallucinated content
    LLM_HALLUCINATION = "llm_hallucination"

    # LLM refused to complete request
    LLM_REFUSAL = "llm_refusal"

    # LLM ignored or drifted from instructions
    LLM_INSTRUCTION_DRIFT = "llm_instruction_drift"

    # Context window exceeded
    CONTEXT_OVERFLOW = "context_overflow"

    # RAG retrieval returned irrelevant results
    RETRIEVAL_MISS = "retrieval_miss"

    # Workflow dependency failed
    WORKFLOW_DEPENDENCY_FAIL = "workflow_dependency_fail"

    # Agent coordination/communication failure
    AGENT_COORDINATION_FAIL = "agent_coordination_fail"

    # Unknown/unclassified failure
    UNKNOWN = "unknown"

    @property
    def is_infrastructure(self) -> bool:
        """Check if this is an infrastructure-level failure."""
        infrastructure_types = {
            FailureType.TOOL_API_ERROR,
            FailureType.TOOL_TIMEOUT,
            FailureType.RESOURCE_EXHAUSTION,
            FailureType.CONNECTION_FAILURE,
            FailureType.RATE_LIMITED,
            FailureType.SERVICE_UNAVAILABLE,
        }
        return self in infrastructure_types

    @property
    def is_application(self) -> bool:
        """Check if this is an application/agentic-level failure."""
        return not self.is_infrastructure and self != FailureType.UNKNOWN


class FailureSeverity(Enum):
    """Severity level of the failure."""

    LOW = "low"  # Minor issue, retry likely to succeed
    MEDIUM = "medium"  # Notable issue, may need intervention
    HIGH = "high"  # Significant issue, needs attention
    CRITICAL = "critical"  # System-breaking, immediate attention required


@dataclass
class FailureContext:
    """
    Rich context captured at failure time for causal decomposition.

    This dataclass captures all relevant information needed to understand
    WHY a failure occurred, not just THAT it occurred.
    """

    # Core identification
    failure_type: FailureType
    severity: FailureSeverity
    error_message: str

    # Timing information
    timestamp: datetime
    latency_ms: float

    # Source information
    tool_name: str | None = None
    model_id: str | None = None
    agent_id: str | None = None
    mission_id: str | None = None

    # Error details
    error_type: str | None = None  # Exception class name
    stack_trace: str | None = None
    http_status_code: int | None = None

    # Input/Output samples (sanitized)
    input_sample: dict[str, Any] | None = None
    output_sample: dict[str, Any] | None = None

    # Execution context
    retry_count: int = 0
    upstream_success: bool = True  # Did the previous step succeed?

    # Sentry integration
    sentry_event_id: str | None = None
    sentry_issue_id: str | None = None
    downstream_impact: list[str] = field(
        default_factory=list
    )  # Affected downstream steps

    # Tracing information
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Tags for filtering/searching
    tags: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["failure_type"] = self.failure_type.value
        data["severity"] = self.severity.value
        data["timestamp"] = self.timestamp.isoformat()
        data["tags"] = list(self.tags)
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureContext":
        """Create from dictionary."""
        data["failure_type"] = FailureType(data["failure_type"])
        data["severity"] = FailureSeverity(data["severity"])
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["tags"] = set(data.get("tags", []))
        return cls(**data)


# ============================================
# Classification Heuristics
# ============================================

# Error message patterns for classification
ERROR_PATTERNS = {
    FailureType.TOOL_API_ERROR: [
        r"api.?error",
        r"external.?service",
        r"upstream.?error",
        r"bad.?gateway",
        r"gateway.?timeout",
    ],
    FailureType.TOOL_TIMEOUT: [
        r"timeout",
        r"timed.?out",
        r"deadline.?exceeded",
        r"execution.?time.?exceeded",
    ],
    FailureType.RESOURCE_EXHAUSTION: [
        r"out.?of.?memory",
        r"memory.?exhausted",
        r"resource.?exhausted",
        r"too.?many.?open.?files",
        r"gpu.?memory",
        r"cuda.?out.?of.?memory",
    ],
    FailureType.CONNECTION_FAILURE: [
        r"connection.?refused",
        r"connection.?reset",
        r"connection.?closed",
        r"network.?unreachable",
        r"no.?route.?to.?host",
        r"socket.?error",
        r"eof.?error",
    ],
    FailureType.RATE_LIMITED: [
        r"rate.?limit",
        r"too.?many.?requests",
        r"429",
        r"quota.?exceeded",
        r"throttl",
    ],
    FailureType.SERVICE_UNAVAILABLE: [
        r"service.?unavailable",
        r"503",
        r"overloaded",
        r"temporarily.?unavailable",
    ],
    FailureType.TOOL_INVALID_INPUT: [
        r"invalid.?parameter",
        r"invalid.?argument",
        r"missing.?required",
        r"validation.?error",
        r"schema.?validation",
        r"type.?error",
        r"value.?error",
    ],
    FailureType.TOOL_INVALID_OUTPUT: [
        r"unexpected.?output",
        r"malformed.?response",
        r"invalid.?response",
        r"parse.?error",
        r"json.?decode.?error",
    ],
    FailureType.LLM_HALLUCINATION: [
        r"hallucinat",
        r"fabricated",
        r"non.?existent",
        r"made.?up",
    ],
    FailureType.LLM_REFUSAL: [
        r"refused",
        r"cannot.?complete",
        r"unable.?to.?assist",
        r"content.?policy",
        r"safety.?guidelines",
    ],
    FailureType.LLM_INSTRUCTION_DRIFT: [
        r"instruction.?drift",
        r"ignored.?instruction",
        r"did.?not.?follow",
        r"unexpected.?behavior",
    ],
    FailureType.CONTEXT_OVERFLOW: [
        r"context.?length",
        r"token.?limit",
        r"max.?tokens",
        r"context.?window",
        r"context.?overflow",
    ],
    FailureType.RETRIEVAL_MISS: [
        r"no.?results.?found",
        r"retrieval.?failed",
        r"no.?relevant",
        r"empty.?retrieval",
    ],
}

# HTTP status code to failure type mapping
HTTP_STATUS_MAP = {
    400: FailureType.TOOL_INVALID_INPUT,
    401: FailureType.CONNECTION_FAILURE,
    403: FailureType.CONNECTION_FAILURE,
    404: FailureType.TOOL_API_ERROR,
    408: FailureType.TOOL_TIMEOUT,
    429: FailureType.RATE_LIMITED,
    500: FailureType.TOOL_API_ERROR,
    502: FailureType.TOOL_API_ERROR,
    503: FailureType.SERVICE_UNAVAILABLE,
    504: FailureType.TOOL_TIMEOUT,
}


def classify_failure(
    error_type: str,
    error_message: str,
    latency_ms: float = 0,
    http_status_code: int | None = None,
    tool_name: str | None = None,
) -> FailureType:
    """
    Heuristic classification of failure type based on error patterns.

    Args:
        error_type: The exception class name (e.g., "TimeoutError", "ValueError")
        error_message: The error message string
        latency_ms: Execution latency in milliseconds
        http_status_code: HTTP status code if applicable
        tool_name: Name of the tool that failed

    Returns:
        FailureType enum value
    """
    error_message_lower = error_message.lower()
    error_type_lower = error_type.lower()

    # Check HTTP status code first (most reliable)
    if http_status_code and http_status_code in HTTP_STATUS_MAP:
        return HTTP_STATUS_MAP[http_status_code]

    # Check for timeout based on latency
    if latency_ms > 30000:  # 30 seconds
        return FailureType.TOOL_TIMEOUT

    # Check error type for common patterns
    if "timeout" in error_type_lower:
        return FailureType.TOOL_TIMEOUT
    if "connection" in error_type_lower:
        return FailureType.CONNECTION_FAILURE
    if "memory" in error_type_lower:
        return FailureType.RESOURCE_EXHAUSTION
    if "value" in error_type_lower or "type" in error_type_lower:
        return FailureType.TOOL_INVALID_INPUT

    # Check error message patterns
    for failure_type, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, error_message_lower):
                return failure_type

    # Check for tool-specific patterns
    if tool_name:
        tool_lower = tool_name.lower()
        if "rag" in tool_lower or "retriev" in tool_lower:
            if "no result" in error_message_lower or "empty" in error_message_lower:
                return FailureType.RETRIEVAL_MISS
        if "llm" in tool_lower or "chat" in tool_lower or "complet" in tool_lower:
            if "context" in error_message_lower or "token" in error_message_lower:
                return FailureType.CONTEXT_OVERFLOW

    return FailureType.UNKNOWN


def determine_severity(
    failure_type: FailureType,
    retry_count: int = 0,
    upstream_success: bool = True,
    downstream_impact_count: int = 0,
) -> FailureSeverity:
    """
    Determine the severity of a failure based on context.

    Args:
        failure_type: The classified failure type
        retry_count: Number of retries attempted
        upstream_success: Whether the previous step succeeded
        downstream_impact_count: Number of affected downstream steps

    Returns:
        FailureSeverity enum value
    """
    # Critical failures
    if failure_type == FailureType.RESOURCE_EXHAUSTION:
        return FailureSeverity.CRITICAL

    if downstream_impact_count > 5:
        return FailureSeverity.CRITICAL

    # High severity
    if (
        failure_type
        in {FailureType.SERVICE_UNAVAILABLE, FailureType.CONNECTION_FAILURE}
        and retry_count > 2
    ):
        return FailureSeverity.HIGH

    if not upstream_success:
        return FailureSeverity.HIGH

    if downstream_impact_count > 2:
        return FailureSeverity.HIGH

    # Medium severity
    if failure_type in {
        FailureType.TOOL_API_ERROR,
        FailureType.RATE_LIMITED,
        FailureType.LLM_HALLUCINATION,
        FailureType.LLM_INSTRUCTION_DRIFT,
        FailureType.CONTEXT_OVERFLOW,
    }:
        return FailureSeverity.MEDIUM

    if retry_count > 0:
        return FailureSeverity.MEDIUM

    # Low severity
    return FailureSeverity.LOW


# ============================================
# Input Sanitization
# ============================================

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "credential",
    "private_key",
    "privatekey",
    "access_token",
    "refresh_token",
    "session_id",
    "cookie",
}

MAX_STRING_LENGTH = 1000
MAX_INPUT_SIZE = 10000  # Max characters for input sample


def sanitize_input(data: Any, depth: int = 0) -> Any:
    """
    Sanitize input data by removing sensitive information and truncating.

    Args:
        data: Input data to sanitize
        depth: Current recursion depth

    Returns:
        Sanitized data
    """
    if depth > 5:  # Prevent deep recursion
        return "<truncated: max depth exceeded>"

    if data is None:
        return None

    if isinstance(data, (str, int, float, bool)):
        if isinstance(data, str) and len(data) > MAX_STRING_LENGTH:
            return data[:MAX_STRING_LENGTH] + "...<truncated>"
        return data

    if isinstance(data, dict):
        sanitized = {}
        total_size = 0
        for key, value in data.items():
            key_lower = key.lower().replace("-", "_").replace(" ", "_")
            if key_lower in SENSITIVE_KEYS:
                sanitized[key] = "<REDACTED>"
            else:
                sanitized[key] = sanitize_input(value, depth + 1)
            total_size += len(str(sanitized[key]))
            if total_size > MAX_INPUT_SIZE:
                break
        return sanitized

    if isinstance(data, (list, tuple)):
        sanitized_list = []
        total_size = 0
        for item in data[:100]:  # Limit list items
            sanitized_list.append(sanitize_input(item, depth + 1))
            total_size += len(str(sanitized_list[-1]))
            if total_size > MAX_INPUT_SIZE:
                break
        return sanitized_list

    # For other types, convert to string and truncate
    str_repr = str(data)
    if len(str_repr) > MAX_STRING_LENGTH:
        return str_repr[:MAX_STRING_LENGTH] + "...<truncated>"
    return str_repr


# ============================================
# Telemetry Capture Functions
# ============================================

# Global reference to observability service (set during initialization)
_observability_service = None
_db_session_factory = None


def set_observability_service(service):
    """Set the global observability service reference."""
    global _observability_service
    _observability_service = service


def set_db_session_factory(factory):
    """Set the database session factory."""
    global _db_session_factory
    _db_session_factory = factory


async def capture_failure_context(
    tool_name: str,
    error: Exception,
    input_data: dict[str, Any] | None = None,
    output_data: dict[str, Any] | None = None,
    latency_ms: float = 0,
    trace_id: str | None = None,
    span_id: str | None = None,
    agent_id: str | None = None,
    mission_id: str | None = None,
    model_id: str | None = None,
    retry_count: int = 0,
    upstream_success: bool = True,
    downstream_impact: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Fire-and-forget telemetry capture for failures.

    This function captures rich failure context and stores it for later
    analysis by the causal decomposition layer. It uses asyncio.create_task()
    for non-blocking execution.

    Args:
        tool_name: Name of the tool that failed
        error: The exception that was raised
        input_data: Input parameters (will be sanitized)
        output_data: Output data if any (will be sanitized)
        latency_ms: Execution latency in milliseconds
        trace_id: Distributed trace ID
        span_id: Span ID for this operation
        agent_id: ID of the agent executing the tool
        mission_id: ID of the mission this is part of
        model_id: ID of the model being used (if LLM-related)
        retry_count: Number of retries attempted
        upstream_success: Whether the previous step succeeded
        downstream_impact: List of affected downstream step IDs
        metadata: Additional metadata
    """
    # Create the failure context
    error_type = type(error).__name__
    error_message = str(error)

    # Get HTTP status code if available
    http_status_code = None
    if hasattr(error, "status_code"):
        http_status_code = error.status_code
    elif hasattr(error, "response") and hasattr(error.response, "status_code"):
        http_status_code = error.response.status_code

    # Classify the failure
    failure_type = classify_failure(
        error_type=error_type,
        error_message=error_message,
        latency_ms=latency_ms,
        http_status_code=http_status_code,
        tool_name=tool_name,
    )

    # Determine severity
    severity = determine_severity(
        failure_type=failure_type,
        retry_count=retry_count,
        upstream_success=upstream_success,
        downstream_impact_count=len(downstream_impact or []),
    )

    # Sanitize input/output
    sanitized_input = sanitize_input(input_data) if input_data else None
    sanitized_output = sanitize_input(output_data) if output_data else None

    # Get stack trace
    stack_trace = traceback.format_exc() if error else None

    # Create FailureContext
    context = FailureContext(
        failure_type=failure_type,
        severity=severity,
        error_message=error_message,
        timestamp=datetime.now(UTC),
        latency_ms=latency_ms,
        tool_name=tool_name,
        model_id=model_id,
        agent_id=agent_id,
        mission_id=mission_id,
        error_type=error_type,
        stack_trace=stack_trace,
        http_status_code=http_status_code,
        input_sample=sanitized_input,
        output_sample=sanitized_output,
        retry_count=retry_count,
        upstream_success=upstream_success,
        downstream_impact=downstream_impact or [],
        trace_id=trace_id,
        span_id=span_id,
        metadata=metadata or {},
        tags={failure_type.value, tool_name, error_type},
    )

    # Fire-and-forget storage
    asyncio.create_task(_store_failure_context(context))

    # Log for debugging
    logger.info(
        f"Captured failure: {failure_type.value} for tool {tool_name} "
        f"(severity: {severity.value}, latency: {latency_ms:.1f}ms)"
    )


async def capture_success_metrics(
    tool_name: str,
    latency_ms: float,
    result_size: int = 0,
    trace_id: str | None = None,
    agent_id: str | None = None,
    mission_id: str | None = None,
    model_id: str | None = None,
) -> None:
    """
    Fire-and-forget telemetry capture for successful executions.

    This captures success metrics for baseline comparison and success rate
    calculations. Less critical than failure capture.

    Args:
        tool_name: Name of the tool that succeeded
        latency_ms: Execution latency in milliseconds
        result_size: Size of the result in bytes/characters
        trace_id: Distributed trace ID
        agent_id: ID of the agent executing the tool
        mission_id: ID of the mission this is part of
        model_id: ID of the model being used
    """
    # Create minimal success context
    success_data = {
        "tool_name": tool_name,
        "latency_ms": latency_ms,
        "result_size": result_size,
        "trace_id": trace_id,
        "agent_id": agent_id,
        "mission_id": mission_id,
        "model_id": model_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "success": True,
    }

    # Fire-and-forget storage
    asyncio.create_task(_store_success_metrics(success_data))


async def _store_failure_context(context: FailureContext) -> None:
    """
    Internal function to store failure context to database.

    This is called via asyncio.create_task() for non-blocking storage.
    """
    try:
        # Capture in Sentry if available
        if SENTRY_AVAILABLE:
            try:
                from app.services.sentry import get_sentry_integration

                sentry = get_sentry_integration()
                if sentry.is_initialized():
                    event_id = sentry.capture_failure_context(context)
                    if event_id:
                        context.sentry_event_id = event_id
                        logger.debug(f"Captured failure in Sentry: {event_id}")
            except Exception as e:
                logger.warning(f"Failed to capture failure in Sentry: {e}")

        # Try to use observability service if available
        if _observability_service:
            await _observability_service.record_failure(context.to_dict())
            return

        # Try to use database session if available
        if _db_session_factory:
            async with _db_session_factory() as session:
                # Import here to avoid circular imports
                from app.models.learning_models import LearningFeedbackDB

                db_record = LearningFeedbackDB(
                    feedback_type="failure_context",
                    content=context.to_dict(),
                    created_at=context.timestamp,
                )
                session.add(db_record)
                await session.commit()
            return

        # Fallback: log to file
        logger.warning(
            f"No storage backend available for failure context. "
            f"Logging to file: {context.to_json()}"
        )

    except Exception as e:
        # Don't let storage failures affect the main execution
        logger.error(f"Failed to store failure context: {e}")


async def _store_success_metrics(data: dict[str, Any]) -> None:
    """
    Internal function to store success metrics.

    This is called via asyncio.create_task() for non-blocking storage.
    """
    try:
        # Try to use observability service if available
        if _observability_service:
            await _observability_service.record_metrics(data)
            return

        # Try to use database session if available
        if _db_session_factory:
            async with _db_session_factory() as session:
                from app.models.learning_models import LearningFeedbackDB

                db_record = LearningFeedbackDB(
                    feedback_type="success_metrics",
                    content=data,
                    created_at=datetime.now(UTC),
                )
                session.add(db_record)
                await session.commit()
            return

        # Fallback: just log
        logger.debug(f"Success metrics: {data}")

    except Exception as e:
        # Don't let storage failures affect the main execution
        logger.error(f"Failed to store success metrics: {e}")


# ============================================
# Utility Functions
# ============================================


def get_failure_summary(failures: list[FailureContext]) -> dict[str, Any]:
    """
    Generate a summary of failures for analysis.

    Args:
        failures: List of FailureContext objects

    Returns:
        Summary dictionary with counts by type, severity, tool, etc.
    """
    if not failures:
        return {"total": 0, "by_type": {}, "by_severity": {}, "by_tool": {}}

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_tool: dict[str, int] = {}

    for f in failures:
        ft = f.failure_type.value
        by_type[ft] = by_type.get(ft, 0) + 1

        sv = f.severity.value
        by_severity[sv] = by_severity.get(sv, 0) + 1

        if f.tool_name:
            by_tool[f.tool_name] = by_tool.get(f.tool_name, 0) + 1

    return {
        "total": len(failures),
        "by_type": by_type,
        "by_severity": by_severity,
        "by_tool": by_tool,
        "infrastructure_count": sum(
            1 for f in failures if f.failure_type.is_infrastructure
        ),
        "application_count": sum(1 for f in failures if f.failure_type.is_application),
    }


# ============================================
# Export
# ============================================

__all__ = [
    # Dataclasses
    "FailureContext",
    "FailureSeverity",
    # Enums
    "FailureType",
    # Capture functions
    "capture_failure_context",
    "capture_success_metrics",
    # Classification functions
    "classify_failure",
    "determine_severity",
    # Utilities
    "get_failure_summary",
    # Sanitization
    "sanitize_input",
    "set_db_session_factory",
    # Setup functions
    "set_observability_service",
]

# Telemetry storage for failure tracking
_failure_telemetry_store: list[dict[str, Any]] = []


def capture_failure_telemetry(
    failure_type: FailureType,
    failure_context: FailureContext,
    severity: FailureSeverity = FailureSeverity.MEDIUM,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Capture failure telemetry for analysis and improvement.
    Fire-and-forget telemetry capture.
    """
    import uuid

    telemetry_id = str(uuid.uuid4())

    telemetry_entry = {
        "id": telemetry_id,
        "failure_type": (
            failure_type.value
            if isinstance(failure_type, FailureType)
            else failure_type
        ),
        "severity": (
            severity.value if isinstance(severity, FailureSeverity) else severity
        ),
        "context": (
            asdict(failure_context)
            if hasattr(failure_context, "__dataclass_fields__")
            else str(failure_context)
        ),
        "metadata": metadata or {},
        "timestamp": datetime.now(UTC).isoformat(),
    }

    _failure_telemetry_store.append(telemetry_entry)
    logger.info(f"Captured failure telemetry: {telemetry_id} - {failure_type}")
    return telemetry_id


def get_failure_telemetry(
    limit: int = 100, failure_type: FailureType | None = None
) -> list[dict[str, Any]]:
    """
    Get stored failure telemetry entries.
    """
    entries = _failure_telemetry_store[-limit:]
    if failure_type:
        entries = [e for e in entries if e.get("failure_type") == failure_type.value]
    return entries
