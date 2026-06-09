"""
Metrics Collector for Autonomous Self-Improvement System.

This module provides real metrics collection from the observability system,
enabling the hypothesis tester to evaluate improvements against actual data
rather than placeholder metrics.

Phase 5A of the Autonomous Self-Improvement Architecture.
"""

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


class MetricType(str, Enum):
    """Types of metrics collected"""

    SUCCESS_RATE = "success_rate"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    COST = "cost"
    THROUGHPUT = "throughput"
    QUALITY = "quality"
    USER_SATISFACTION = "user_satisfaction"
    TOKEN_USAGE = "token_usage"
    CUSTOM = "custom"


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: datetime
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """A time series of metric points."""

    metric_name: str
    points: list[MetricPoint] = field(default_factory=list)

    def add_point(self, value: float, labels: dict[str, str] = None):
        """Add a point to the series."""
        self.points.append(
            MetricPoint(
                timestamp=datetime.now(UTC),
                value=value,
                labels=labels or {},
            )
        )

    def get_values(self) -> list[float]:
        """Get all values as a list."""
        return [p.value for p in self.points]

    def get_average(self) -> float | None:
        """Get average value."""
        values = self.get_values()
        return statistics.mean(values) if values else None

    def get_percentile(self, percentile: float) -> float | None:
        """Get a percentile value (e.g., 95 for p95)."""
        values = sorted(self.get_values())
        if not values:
            return None
        index = int(len(values) * percentile / 100)
        index = min(index, len(values) - 1)
        return values[index]


@dataclass
class AgentMetrics:
    """Aggregated metrics for an agent."""

    agent_id: str
    time_window: timedelta

    # Success metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Latency metrics (in milliseconds)
    latencies: list[float] = field(default_factory=list)

    # Error metrics
    errors_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Tool metrics
    tool_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tool_errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 1.0  # No requests = perfect success
        return self.successful_requests / self.total_requests

    @property
    def error_rate(self) -> float:
        """Calculate error rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    @property
    def latency_p50(self) -> float:
        """Get median latency."""
        return self._percentile(50)

    @property
    def latency_p95(self) -> float:
        """Get 95th percentile latency."""
        return self._percentile(95)

    @property
    def latency_p99(self) -> float:
        """Get 99th percentile latency."""
        return self._percentile(99)

    @property
    def avg_latency(self) -> float:
        """Get average latency."""
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    def _percentile(self, p: float) -> float:
        """Calculate percentile of latencies."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * p / 100)
        index = min(index, len(sorted_latencies) - 1)
        return sorted_latencies[index]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "agent_id": self.agent_id,
            "time_window_seconds": self.time_window.total_seconds(),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "latency_avg": self.avg_latency,
            "latency_p50": self.latency_p50,
            "latency_p95": self.latency_p95,
            "latency_p99": self.latency_p99,
            "errors_by_type": dict(self.errors_by_type),
            "tool_calls": dict(self.tool_calls),
            "tool_errors": dict(self.tool_errors),
        }


# ============================================================================
# METRICS COLLECTOR
# ============================================================================


class MetricsCollector:
    """
    Collects real metrics from the observability system.

    This class queries the existing observability infrastructure to get
    actual performance data for hypothesis testing and improvement evaluation.
    """

    def __init__(self, observability_service=None):
        """
        Initialize the metrics collector.

        Args:
            observability_service: The observability service to query
        """
        self.observability = observability_service
        self._metric_cache: dict[str, MetricSeries] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._last_cache_clear = datetime.now(UTC)

        # In-memory metrics storage (fallback when observability not available)
        self._metrics_store: dict[str, list[MetricPoint]] = defaultdict(list)

    async def get_metrics(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        time_window: timedelta = timedelta(hours=1),
    ) -> dict[str, float]:
        """
        Get aggregated metrics for the specified time window.

        Args:
            agent_id: Optional agent ID to filter by
            start_time: Start of time window (defaults to now - time_window)
            end_time: End of time window (defaults to now)
            time_window: Time window if start_time not specified

        Returns:
            Dictionary of metric names to values
        """
        if end_time is None:
            end_time = datetime.now(UTC)
        if start_time is None:
            start_time = end_time - time_window

        # Try to get from observability service first
        if self.observability:
            try:
                return await self._query_observability(agent_id, start_time, end_time)
            except Exception as e:
                logger.warning('Failed to query observability: %s', e)

        # Fall back to in-memory metrics
        return self._get_from_memory(agent_id, start_time, end_time)

    async def get_agent_metrics(
        self,
        agent_id: str,
        time_window: timedelta = timedelta(hours=1),
    ) -> AgentMetrics:
        """
        Get detailed metrics for a specific agent.

        Args:
            agent_id: The agent ID
            time_window: Time window to aggregate over

        Returns:
            AgentMetrics with detailed statistics
        """
        end_time = datetime.now(UTC)
        start_time = end_time - time_window

        metrics = AgentMetrics(
            agent_id=agent_id,
            time_window=time_window,
        )

        # Query spans/metrics from observability
        if self.observability:
            try:
                await self._populate_agent_metrics_from_observability(
                    metrics, start_time, end_time
                )
            except Exception as e:
                logger.warning('Failed to populate from observability: %s', e)
                self._populate_agent_metrics_from_memory(metrics, start_time, end_time)
        else:
            self._populate_agent_metrics_from_memory(metrics, start_time, end_time)

        return metrics

    async def get_success_rate(
        self,
        agent_id: str | None = None,
        time_window: timedelta = timedelta(hours=1),
    ) -> float:
        """Get success rate (0.0 to 1.0)."""
        metrics = await self.get_metrics(agent_id, time_window=time_window)
        return metrics.get("success_rate", 1.0)

    async def get_latency_percentile(
        self,
        percentile: float,
        agent_id: str | None = None,
        time_window: timedelta = timedelta(hours=1),
    ) -> float:
        """Get latency at a specific percentile (in milliseconds)."""
        metrics = await self.get_metrics(agent_id, time_window=time_window)
        key = f"latency_p{int(percentile)}"
        return metrics.get(key, metrics.get("latency_p95", 0.0))

    async def get_error_rate(
        self,
        agent_id: str | None = None,
        time_window: timedelta = timedelta(hours=1),
    ) -> float:
        """Get error rate (0.0 to 1.0)."""
        metrics = await self.get_metrics(agent_id, time_window=time_window)
        return metrics.get("error_rate", 0.0)

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a metric value.

        Args:
            metric_name: Name of the metric
            value: Metric value
            labels: Optional labels for the metric
        """
        point = MetricPoint(
            timestamp=datetime.now(UTC),
            value=value,
            labels=labels or {},
        )

        # Store in memory
        self._metrics_store[metric_name].append(point)

        # Also push to observability if available
        if self.observability:
            try:
                await self._push_to_observability(metric_name, point)
            except Exception as e:
                logger.warning('Failed to push to observability: %s', e)

        # Periodic cache cleanup
        if (datetime.now(UTC) - self._last_cache_clear) > self._cache_ttl:
            self._cleanup_old_metrics()

    async def record_request(
        self,
        agent_id: str,
        success: bool,
        latency_ms: float,
        error_type: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """
        Record a request outcome.

        Args:
            agent_id: Agent that made the request
            success: Whether the request succeeded
            latency_ms: Request latency in milliseconds
            error_type: Error type if failed
            tool_name: Tool name if applicable
        """
        labels = {"agent_id": agent_id}
        if tool_name:
            labels["tool"] = tool_name
        if error_type:
            labels["error_type"] = error_type

        # Record individual metrics
        await self.record_metric("requests_total", 1, labels)
        await self.record_metric("latency_ms", latency_ms, labels)

        if success:
            await self.record_metric("requests_success", 1, labels)
        else:
            await self.record_metric("requests_failed", 1, labels)
            if error_type:
                await self.record_metric(f"errors_{error_type}", 1, labels)

        if tool_name:
            await self.record_metric(f"tool_calls_{tool_name}", 1, labels)
            if not success:
                await self.record_metric(f"tool_errors_{tool_name}", 1, labels)

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    async def _query_observability(
        self,
        agent_id: str | None,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, float]:
        """Query metrics from the observability service."""
        # This would integrate with the actual observability system
        # For now, return aggregated in-memory metrics

        if hasattr(self.observability, "query_metrics"):
            # Use observability service's query method
            return await self.observability.query_metrics(
                start_time=start_time,
                end_time=end_time,
                agent_id=agent_id,
            )

        # Fall back to in-memory
        return self._get_from_memory(agent_id, start_time, end_time)

    async def _push_to_observability(
        self,
        metric_name: str,
        point: MetricPoint,
    ) -> None:
        """Push a metric to the observability service."""
        if hasattr(self.observability, "record_metric"):
            await self.observability.record_metric(
                metric_name=metric_name,
                value=point.value,
                labels=point.labels,
            )

    async def _populate_agent_metrics_from_observability(
        self,
        metrics: AgentMetrics,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Populate AgentMetrics from observability service."""
        if hasattr(self.observability, "get_agent_metrics"):
            obs_metrics = await self.observability.get_agent_metrics(
                agent_id=metrics.agent_id,
                start_time=start_time,
                end_time=end_time,
            )

            # Map observability metrics to AgentMetrics
            metrics.total_requests = obs_metrics.get("total_requests", 0)
            metrics.successful_requests = obs_metrics.get("successful_requests", 0)
            metrics.failed_requests = obs_metrics.get("failed_requests", 0)
            metrics.latencies = obs_metrics.get("latencies", [])
            metrics.errors_by_type = defaultdict(
                int, obs_metrics.get("errors_by_type", {})
            )
            metrics.tool_calls = defaultdict(int, obs_metrics.get("tool_calls", {}))
            metrics.tool_errors = defaultdict(int, obs_metrics.get("tool_errors", {}))

    def _populate_agent_metrics_from_memory(
        self,
        metrics: AgentMetrics,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Populate AgentMetrics from in-memory storage."""
        agent_id = metrics.agent_id

        # Get all metric points in time window
        for metric_name, points in self._metrics_store.items():
            for point in points:
                if point.timestamp < start_time or point.timestamp > end_time:
                    continue

                if point.labels.get("agent_id") != agent_id:
                    continue

                if metric_name == "requests_total":
                    metrics.total_requests += 1
                elif metric_name == "requests_success":
                    metrics.successful_requests += 1
                elif metric_name == "requests_failed":
                    metrics.failed_requests += 1
                elif metric_name == "latency_ms":
                    metrics.latencies.append(point.value)
                elif metric_name.startswith("errors_"):
                    error_type = metric_name[7:]  # Remove "errors_" prefix
                    metrics.errors_by_type[error_type] += int(point.value)
                elif metric_name.startswith("tool_calls_"):
                    tool = metric_name[11:]  # Remove "tool_calls_" prefix
                    metrics.tool_calls[tool] += int(point.value)
                elif metric_name.startswith("tool_errors_"):
                    tool = metric_name[12:]  # Remove "tool_errors_" prefix
                    metrics.tool_errors[tool] += int(point.value)

    def _get_from_memory(
        self,
        agent_id: str | None,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, float]:
        """Get aggregated metrics from in-memory storage."""
        result = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "latencies": [],
        }

        for metric_name, points in self._metrics_store.items():
            for point in points:
                if point.timestamp < start_time or point.timestamp > end_time:
                    continue

                if agent_id and point.labels.get("agent_id") != agent_id:
                    continue

                if metric_name == "requests_total":
                    result["total_requests"] += 1
                elif metric_name == "requests_success":
                    result["successful_requests"] += 1
                elif metric_name == "requests_failed":
                    result["failed_requests"] += 1
                elif metric_name == "latency_ms":
                    result["latencies"].append(point.value)

        # Calculate derived metrics
        total = result["total_requests"]
        latencies = result["latencies"]

        return {
            "success_rate": result["successful_requests"] / total if total > 0 else 1.0,
            "error_rate": result["failed_requests"] / total if total > 0 else 0.0,
            "latency_avg": statistics.mean(latencies) if latencies else 0.0,
            "latency_p50": self._percentile(latencies, 50),
            "latency_p95": self._percentile(latencies, 95),
            "latency_p99": self._percentile(latencies, 99),
            "total_requests": total,
            "successful_requests": result["successful_requests"],
            "failed_requests": result["failed_requests"],
        }

    def _percentile(self, values: list[float], p: float) -> float:
        """Calculate percentile of a list."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * p / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def _cleanup_old_metrics(self) -> None:
        """Remove metrics older than cache TTL."""
        cutoff = datetime.now(UTC) - timedelta(hours=24)  # Keep 24 hours

        for metric_name in list(self._metrics_store.keys()):
            self._metrics_store[metric_name] = [
                p for p in self._metrics_store[metric_name] if p.timestamp > cutoff
            ]

        self._last_cache_clear = datetime.now(UTC)
        logger.debug("Cleaned up old metrics from memory")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the singleton metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def initialize_metrics_collector(observability_service=None) -> MetricsCollector:
    """Initialize the metrics collector with an observability service."""
    global _metrics_collector
    _metrics_collector = MetricsCollector(observability_service)
    return _metrics_collector
