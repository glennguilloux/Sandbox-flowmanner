"""LangGraph Trace Emitter for real-time execution visualization.

This module provides trace emission capabilities for LangGraph execution,
integrating with Socket.IO for real-time updates to the frontend.
"""

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.nexus.observability import Span, SpanKind

logger = logging.getLogger(__name__)


@dataclass
class TraceEvent:
    """Event emitted during execution trace."""

    event_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    event_type: str  # 'span_start', 'span_end', 'token', 'tool_call', 'error'
    timestamp: str
    node_name: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LangGraphTraceEmitter:
    """Emits trace events during LangGraph execution.

    Usage:
        emitter = LangGraphTraceEmitter(trace_id="xxx", thread_id="yyy")

        # Decorate node methods before compile
        @emitter.trace_node("agent_node")
        async def agent_node(state):
            ...

        # Or use context manager for streaming
        async with emitter.span("llm_call", input_snapshot={"prompt": prompt}):
            async for chunk in llm.astream(prompt):
                emitter.emit_token(chunk)
    """

    def __init__(
        self,
        trace_id: str | None = None,
        thread_id: str | None = None,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        socket_namespace=None,
    ):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.thread_id = thread_id
        self.workflow_id = workflow_id
        self.agent_id = agent_id
        self.socket_namespace = socket_namespace

        self._spans: dict[str, Span] = {}
        self._span_stack: list[str] = []  # Track nested spans
        self._token_buffer: list[str] = []
        self._last_token_emit: float = 0
        self._token_emit_interval: float = 0.05  # 50ms batching

    def set_socket_namespace(self, namespace):
        """Set the Socket.IO namespace for emission."""
        self.socket_namespace = namespace

    def _get_socket_namespace(self):
        """Get socket namespace, lazy loading if needed."""
        if self.socket_namespace is None:
            try:
                from app.api.v1.agent_socket import get_agent_namespace

                self.socket_namespace = get_agent_namespace()
            except ImportError:
                logger.warning("Socket namespace not available")
        return self.socket_namespace

    def _emit_event(self, event: TraceEvent):
        """Emit a trace event via Socket.IO."""
        namespace = self._get_socket_namespace()
        if namespace is None:
            return

        room = f"trace:{self.trace_id}"
        event_data = event.to_dict()

        # Use async emit if in async context
        try:
            loop = asyncio.get_running_loop()
            # Schedule the emit on the event loop
            asyncio.create_task(namespace.emit("trace_event", event_data, room=room))
        except RuntimeError:
            # No running loop, emit synchronously (for sync contexts)
            logger.debug('No async context, queuing event: %s', event.event_type)

    def start_span(
        self,
        operation_name: str,
        parent_span_id: str | None = None,
        node_id: str | None = None,
        input_snapshot: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new trace span."""
        span_id = str(uuid.uuid4())

        # Use parent from stack if not specified
        if parent_span_id is None and self._span_stack:
            parent_span_id = self._span_stack[-1]

        span = Span(
            span_id=span_id,
            trace_id=self.trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            kind=SpanKind.INTERNAL,
            thread_id=self.thread_id,
            workflow_id=self.workflow_id,
            node_id=node_id,
            input_snapshot=input_snapshot,
            correlation_id=str(uuid.uuid4()),
        )

        self._spans[span_id] = span
        self._span_stack.append(span_id)

        # Emit start event
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=self.trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            event_type="span_start",
            timestamp=datetime.now(UTC).isoformat(),
            node_name=operation_name,
            data={"input": input_snapshot, "node_id": node_id},
        )
        self._emit_event(event)

        return span

    def end_span(
        self,
        span: Span,
        output_snapshot: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        """End a trace span."""
        span.finish()
        span.output_snapshot = output_snapshot

        if error:
            span.set_error(error)

        # Remove from stack
        if span.span_id in self._span_stack:
            self._span_stack.remove(span.span_id)

        # Emit end event
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=self.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            event_type="span_end",
            timestamp=datetime.now(UTC).isoformat(),
            node_name=span.operation_name,
            data={
                "output": output_snapshot,
                "duration_ms": span.duration_ms,
                "status": span.status.value,
                "error": str(error) if error else None,
            },
        )
        self._emit_event(event)

    def emit_token(self, token: str):
        """Emit a streaming token event."""
        import time

        current_time = time.time()

        # Buffer tokens for batch emission
        self._token_buffer.append(token)

        # Emit batch if interval elapsed or buffer is large
        if (
            current_time - self._last_token_emit > self._token_emit_interval
            or len(self._token_buffer) >= 10
        ):
            event = TraceEvent(
                event_id=str(uuid.uuid4()),
                trace_id=self.trace_id,
                span_id=self._span_stack[-1] if self._span_stack else None,
                parent_span_id=None,
                event_type="tokens",
                timestamp=datetime.now(UTC).isoformat(),
                node_name="streaming",
                data={
                    "tokens": "".join(self._token_buffer),
                    "count": len(self._token_buffer),
                },
            )
            self._emit_event(event)
            self._token_buffer = []
            self._last_token_emit = current_time

    def emit_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: Any | None = None,
        error: str | None = None,
    ):
        """Emit a tool call event."""
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=self.trace_id,
            span_id=self._span_stack[-1] if self._span_stack else None,
            parent_span_id=None,
            event_type="tool_call",
            timestamp=datetime.now(UTC).isoformat(),
            node_name=tool_name,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_output": tool_output,
                "error": error,
            },
        )
        self._emit_event(event)

    def trace_node(self, node_name: str):
        """Decorator to trace a LangGraph node.

        Usage:
            @emitter.trace_node("agent_node")
            async def agent_node(state):
                ...
        """

        def decorator(func):
            async def wrapper(state):
                span = self.start_span(
                    operation_name=node_name,
                    node_id=node_name,
                    input_snapshot={
                        "state_keys": (
                            list(state.keys()) if isinstance(state, dict) else None
                        )
                    },
                )
                try:
                    result = await func(state)
                    self.end_span(
                        span, output_snapshot={"result_type": type(result).__name__}
                    )
                    return result
                except Exception as e:
                    self.end_span(span, error=e)
                    raise

            return wrapper

        return decorator

    def span(
        self,
        operation_name: str,
        node_id: str | None = None,
        input_snapshot: dict[str, Any] | None = None,
    ):
        """Context manager for tracing a span.

        Usage:
            async with emitter.span("llm_call", input_snapshot={"prompt": prompt}):
                result = await llm.ainvoke(prompt)
        """
        return _SpanContextManager(self, operation_name, node_id, input_snapshot)


class _SpanContextManager:
    """Context manager for trace spans."""

    def __init__(
        self,
        emitter: LangGraphTraceEmitter,
        operation_name: str,
        node_id: str | None,
        input_snapshot: dict[str, Any] | None,
    ):
        self.emitter = emitter
        self.operation_name = operation_name
        self.node_id = node_id
        self.input_snapshot = input_snapshot
        self.span: Span | None = None

    async def __aenter__(self):
        self.span = self.emitter.start_span(
            self.operation_name,
            node_id=self.node_id,
            input_snapshot=self.input_snapshot,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.emitter.end_span(self.span, error=exc_val)
        else:
            self.emitter.end_span(self.span)
        return False


def create_trace_emitter(
    thread_id: str | None = None,
    workflow_id: str | None = None,
    agent_id: str | None = None,
) -> LangGraphTraceEmitter:
    """Factory function to create a trace emitter."""
    return LangGraphTraceEmitter(
        thread_id=thread_id, workflow_id=workflow_id, agent_id=agent_id
    )
