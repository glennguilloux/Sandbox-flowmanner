"""
Observability & Tracing - Distributed tracing and performance monitoring

Provides comprehensive observability for the MetaLoop agent system including
distributed tracing, performance metrics, error tracking, and OpenTelemetry integration.
"""

import asyncio
import json
import logging
import traceback
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Optional OpenTelemetry support
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None


class SpanKind(Enum):
    """Type of span operation"""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(Enum):
    """Span execution status"""

    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class Span:
    """Represents a single trace span"""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    operation_name: str
    kind: SpanKind = SpanKind.INTERNAL
    status: SpanStatus = SpanStatus.UNSET
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None
    duration_ms: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    agent_id: str | None = None
    tool_name: str | None = None
    error: str | None = None
    error_stack: str | None = None
    thread_id: str | None = None
    workflow_id: str | None = None
    node_id: str | None = None
    input_snapshot: dict[str, Any] | None = None
    output_snapshot: dict[str, Any] | None = None
    correlation_id: str | None = None

    def add_event(self, name: str, attributes: dict[str, Any] | None = None):
        """Add an event to the span"""
        self.events.append(
            {
                "name": name,
                "timestamp": datetime.now(UTC).isoformat(),
                "attributes": attributes or {},
            }
        )

    def set_attribute(self, key: str, value: Any):
        """Set an attribute on the span"""
        self.attributes[key] = value

    def set_error(self, error: Exception):
        """Record an error on the span"""
        self.status = SpanStatus.ERROR
        self.error = str(error)
        self.error_stack = traceback.format_exc()
        self.add_event(
            "exception", {"type": type(error).__name__, "message": str(error)}
        )

    def finish(self):
        """Mark span as complete"""
        self.end_time = datetime.now(UTC)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        if self.status == SpanStatus.UNSET:
            self.status = SpanStatus.OK

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary"""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "kind": self.kind.value,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "error": self.error,
            "error_stack": self.error_stack,
            "thread_id": self.thread_id,
            "workflow_id": self.workflow_id,
            "node_id": self.node_id,
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "correlation_id": self.correlation_id,
        }


@dataclass
class Trace:
    """Complete trace with all spans"""

    trace_id: str
    root_span: Span | None = None
    spans: list[Span] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None
    total_duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_span(self, span: Span):
        """Add a span to the trace"""
        self.spans.append(span)

    def finish(self):
        """Mark trace as complete"""
        self.end_time = datetime.now(UTC)
        self.total_duration_ms = (
            self.end_time - self.start_time
        ).total_seconds() * 1000

    def get_span_tree(self) -> dict[str, Any]:
        """Build hierarchical span tree"""
        span_map = {s.span_id: s.to_dict() for s in self.spans}
        root_spans = []

        for span_dict in span_map.values():
            parent_id = span_dict.get("parent_span_id")
            if parent_id and parent_id in span_map:
                parent = span_map[parent_id]
                if "children" not in parent:
                    parent["children"] = []
                parent["children"].append(span_dict)
            else:
                root_spans.append(span_dict)

        return {"trace_id": self.trace_id, "spans": root_spans}


@dataclass
class Metric:
    """Performance metric data point"""

    name: str
    value: float
    metric_type: str  # "counter", "gauge", "histogram"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: dict[str, str] = field(default_factory=dict)
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "unit": self.unit,
        }


@dataclass
class ErrorRecord:
    """Error tracking record"""

    error_id: str
    error_type: str
    message: str
    stack_trace: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_id: str | None = None
    tool_name: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "trace_id": self.trace_id,
            "resolved": self.resolved,
        }


@dataclass
class PerformanceStats:
    """Aggregated performance statistics"""

    operation: str
    count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0

    def update(self, duration_ms: float, is_error: bool = False):
        """Update stats with new measurement"""
        self.count += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.avg_duration_ms = self.total_duration_ms / self.count
        if is_error:
            self.error_count += 1
        self.error_rate = self.error_count / self.count


class ObservabilityService:
    """
    Central observability service for distributed tracing and metrics.

    Features:
    - Distributed tracing with span hierarchy
    - Performance metrics collection
    - Error tracking and alerting
    - Debug logging with context
    - OpenTelemetry integration
    """

    def __init__(self, service_name: str = "metaloop-agent"):
        self.service_name = service_name
        self._traces: dict[str, Trace] = {}
        self._active_spans: dict[str, Span] = {}  # span_id -> Span
        self._metrics: list[Metric] = []
        self._metrics_by_name: dict[str, list[Metric]] = defaultdict(list)
        self._errors: list[ErrorRecord] = []
        self._performance_stats: dict[str, PerformanceStats] = {}
        self._context: dict[str, Any] = {}  # Current trace context
        self._lock = asyncio.Lock()

        # OpenTelemetry setup
        self._otel_tracer = None
        if OTEL_AVAILABLE:
            try:
                provider = TracerProvider()
                self._otel_tracer = trace.get_tracer(service_name)
                logger.info("OpenTelemetry tracer initialized")
            except Exception as e:
                logger.warning("Failed to initialize OpenTelemetry: %s", e)

        # Alert handlers
        self._error_handlers: list[Callable[[ErrorRecord], Awaitable[None]]] = []
        self._performance_handlers: list[Callable[[str, float], Awaitable[None]]] = []

    def register_error_handler(self, handler: Callable[[ErrorRecord], Awaitable[None]]):
        """Register handler for error alerts"""
        self._error_handlers.append(handler)

    def register_performance_handler(
        self, handler: Callable[[str, float], Awaitable[None]]
    ):
        """Register handler for performance alerts"""
        self._performance_handlers.append(handler)

    async def _send_error_alert(self, error: ErrorRecord):
        """Send error to registered handlers"""
        for handler in self._error_handlers:
            try:
                await handler(error)
            except Exception as e:
                logger.error("Error handler failed: %s", e)

    def _generate_id(self) -> str:
        """Generate unique ID"""
        return uuid.uuid4().hex[:16]

    def start_trace(
        self,
        operation_name: str,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Trace:
        """
        Start a new trace.

        Args:
            operation_name: Name of the operation being traced
            agent_id: Agent initiating the trace
            metadata: Additional metadata

        Returns:
            New Trace object
        """
        trace_id = self._generate_id()
        trace_obj = Trace(trace_id=trace_id, metadata=metadata or {})

        if agent_id:
            trace_obj.metadata["agent_id"] = agent_id

        self._traces[trace_id] = trace_obj
        self._context["current_trace_id"] = trace_id

        logger.debug("Started trace %s: %s", trace_id, operation_name)
        return trace_obj

    def start_span(
        self,
        operation_name: str,
        parent_span: Span | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        agent_id: str | None = None,
        tool_name: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """
        Start a new span.

        Args:
            operation_name: Name of the operation
            parent_span: Parent span (if nested)
            kind: Type of span
            agent_id: Agent executing the span
            tool_name: Tool being executed
            attributes: Initial attributes

        Returns:
            New Span object
        """
        span_id = self._generate_id()
        trace_id = self._context.get("current_trace_id", self._generate_id())
        parent_span_id = (
            parent_span.span_id if parent_span else self._context.get("current_span_id")
        )

        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            kind=kind,
            agent_id=agent_id,
            tool_name=tool_name,
            attributes=attributes or {},
        )

        self._active_spans[span_id] = span
        self._context["current_span_id"] = span_id

        # Add to trace if exists
        if trace_id in self._traces:
            self._traces[trace_id].add_span(span)

        # OpenTelemetry span
        otel_span = None
        if self._otel_tracer:
            try:
                otel_span = self._otel_tracer.start_span(operation_name)
                span.attributes["otel_span"] = otel_span
            except Exception as e:
                logger.debug("OpenTelemetry span creation failed: %s", e)

        logger.debug("Started span %s: %s", span_id, operation_name)
        return span

    def end_span(self, span: Span, error: Exception | None = None):
        """
        End a span.

        Args:
            span: Span to end
            error: Optional error that occurred
        """
        if error:
            span.set_error(error)

        span.finish()

        # Update performance stats
        if span.operation_name not in self._performance_stats:
            self._performance_stats[span.operation_name] = PerformanceStats(
                operation=span.operation_name
            )

        self._performance_stats[span.operation_name].update(
            span.duration_ms or 0, is_error=(span.status == SpanStatus.ERROR)
        )

        # End OpenTelemetry span
        otel_span = span.attributes.pop("otel_span", None)
        if otel_span and OTEL_AVAILABLE:
            try:
                if span.status == SpanStatus.ERROR:
                    otel_span.set_status(Status(StatusCode.ERROR))
                else:
                    otel_span.set_status(Status(StatusCode.OK))
                otel_span.end()
            except Exception as e:
                logger.debug("OpenTelemetry span end failed: %s", e)

        # Remove from active spans
        if span.span_id in self._active_spans:
            del self._active_spans[span.span_id]

        # Clear context if this was the current span
        if self._context.get("current_span_id") == span.span_id:
            self._context.pop("current_span_id", None)

        logger.debug(
            "Ended span %s: %s (%.2fms)",
            span.span_id,
            span.operation_name,
            span.duration_ms,
        )

    def end_trace(self, trace: Trace):
        """End a trace"""
        trace.finish()
        self._context.pop("current_trace_id", None)
        logger.debug("Ended trace %s (%.2fms)", trace.trace_id, trace.total_duration_ms)

    @asynccontextmanager
    async def trace_operation(
        self,
        operation_name: str,
        agent_id: str | None = None,
        tool_name: str | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Context manager for tracing an operation.

        Usage:
            async with observability.trace_operation("query_rag", agent_id="agent-1"):
                # ... operation code ...
        """
        span = self.start_span(
            operation_name=operation_name,
            agent_id=agent_id,
            tool_name=tool_name,
            attributes=attributes,
        )

        try:
            yield span
        except Exception as e:
            span.set_error(e)
            await self.record_error(
                error=e,
                agent_id=agent_id,
                tool_name=tool_name,
                trace_id=span.trace_id,
                span_id=span.span_id,
            )
            raise
        finally:
            self.end_span(span)

    async def record_metric(
        self,
        name: str,
        value: float,
        metric_type: str = "gauge",
        labels: dict[str, str] | None = None,
        unit: str = "",
    ):
        """
        Record a metric.

        Args:
            name: Metric name
            value: Metric value
            metric_type: "counter", "gauge", or "histogram"
            labels: Optional labels for filtering
            unit: Unit of measurement
        """
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels or {},
            unit=unit,
        )

        async with self._lock:
            self._metrics.append(metric)
            self._metrics_by_name[name].append(metric)

            # Keep only last 10000 metrics per name
            if len(self._metrics_by_name[name]) > 10000:
                self._metrics_by_name[name] = self._metrics_by_name[name][-10000:]

        logger.debug("Recorded metric %s=%s", name, value)

    async def increment_counter(self, name: str, labels: dict[str, str] | None = None):
        """Increment a counter metric"""
        current = sum(m.value for m in self._metrics_by_name.get(name, []))
        await self.record_metric(name, current + 1, "counter", labels)

    async def record_error(
        self,
        error: Exception,
        agent_id: str | None = None,
        tool_name: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ErrorRecord:
        """
        Record an error.

        Args:
            error: The exception that occurred
            agent_id: Agent where error occurred
            tool_name: Tool where error occurred
            trace_id: Associated trace ID
            span_id: Associated span ID
            context: Additional context

        Returns:
            ErrorRecord for the error
        """
        error_record = ErrorRecord(
            error_id=self._generate_id(),
            error_type=type(error).__name__,
            message=str(error),
            stack_trace=traceback.format_exc(),
            agent_id=agent_id,
            tool_name=tool_name,
            trace_id=trace_id,
            span_id=span_id,
            context=context or {},
        )

        async with self._lock:
            self._errors.append(error_record)

            # Keep only last 1000 errors
            if len(self._errors) > 1000:
                self._errors = self._errors[-1000:]

        logger.error(
            "Recorded error %s: %s: %s",
            error_record.error_id,
            error_record.error_type,
            error_record.message,
        )

        # Send alert
        await self._send_error_alert(error_record)

        return error_record

    async def get_trace(self, trace_id: str) -> Trace | None:
        """Get a trace by ID"""
        return self._traces.get(trace_id)

    async def get_span(self, span_id: str) -> Span | None:
        """Get a span by ID"""
        return self._active_spans.get(span_id)

    async def get_metrics(
        self,
        name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Metric]:
        """Get metrics, optionally filtered"""
        metrics = self._metrics_by_name.get(name, []) if name else self._metrics

        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]

        return metrics

    async def get_errors(
        self,
        agent_id: str | None = None,
        tool_name: str | None = None,
        resolved: bool | None = None,
        limit: int = 100,
    ) -> list[ErrorRecord]:
        """Get errors, optionally filtered"""
        errors = self._errors

        if agent_id:
            errors = [e for e in errors if e.agent_id == agent_id]
        if tool_name:
            errors = [e for e in errors if e.tool_name == tool_name]
        if resolved is not None:
            errors = [e for e in errors if e.resolved == resolved]

        return errors[-limit:]

    async def get_performance_stats(
        self, operation: str | None = None
    ) -> dict[str, Any]:
        """Get performance statistics"""
        if operation:
            stats = self._performance_stats.get(operation)
            return stats.__dict__ if stats else {}

        return {op: stats.__dict__ for op, stats in self._performance_stats.items()}

    async def get_health_summary(self) -> dict[str, Any]:
        """Get overall system health summary"""
        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)

        recent_errors = [e for e in self._errors if e.timestamp >= hour_ago]
        recent_traces = [t for t in self._traces.values() if t.start_time >= hour_ago]

        error_rate = len(recent_errors) / max(len(recent_traces), 1)

        # Calculate average latency
        latencies = []
        for stats in self._performance_stats.values():
            if stats.avg_duration_ms > 0:
                latencies.append(stats.avg_duration_ms)

        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "status": "healthy" if error_rate < 0.1 else "degraded",
            "active_traces": len(self._traces),
            "active_spans": len(self._active_spans),
            "total_metrics": len(self._metrics),
            "total_errors": len(self._errors),
            "recent_errors_1h": len(recent_errors),
            "error_rate_1h": error_rate,
            "avg_latency_ms": avg_latency,
            "operations_tracked": len(self._performance_stats),
            "otel_enabled": OTEL_AVAILABLE and self._otel_tracer is not None,
        }

    def log_with_context(self, level: str, message: str, **kwargs):
        """
        Log with current trace context.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            **kwargs: Additional context
        """
        context = {
            "trace_id": self._context.get("current_trace_id"),
            "span_id": self._context.get("current_span_id"),
            **kwargs,
        }

        log_msg = f"[{context.get('trace_id', 'no-trace')}] {message}"

        if level == "debug":
            logger.debug(log_msg, extra=context)
        elif level == "info":
            logger.info(log_msg, extra=context)
        elif level == "warning":
            logger.warning(log_msg, extra=context)
        elif level == "error":
            logger.error(log_msg, extra=context)

    async def export_traces(self, format: str = "json") -> str:
        """Export traces for external analysis"""
        traces_data = []
        for trace in self._traces.values():
            traces_data.append(trace.get_span_tree())

        if format == "json":
            return json.dumps(traces_data, indent=2, default=str)

        return str(traces_data)


# Singleton instance
_observability_service: ObservabilityService | None = None


def get_observability_service() -> ObservabilityService:
    """Get the singleton ObservabilityService instance"""
    global _observability_service
    if _observability_service is None:
        _observability_service = ObservabilityService()
        logger.info("Initialized ObservabilityService singleton")
    return _observability_service
