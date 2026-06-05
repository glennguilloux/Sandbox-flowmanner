"""
Temporal Pattern Analyzer for Autonomous Self-Improvement System.

This module detects time-based patterns in failures and successes,
enabling proactive improvements before issues occur.

Phase 6E of the Autonomous Self-Improvement Architecture.
"""

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Import from previous phases
from .failure_types import FailureSeverity, FailureType

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class PatternFrequency(str, Enum):
    """Frequency of temporal patterns."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    IRREGULAR = "irregular"


class PatternDirection(str, Enum):
    """Direction of metric change."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    SPIKE = "spike"
    DROP = "drop"


class AnomalyType(str, Enum):
    """Types of anomalies."""

    SPIKE = "spike"  # Sudden increase
    DROP = "drop"  # Sudden decrease
    TREND_CHANGE = "trend_change"  # Direction change
    OUTLIER = "outlier"  # Single point outlier
    CLUSTER = "cluster"  # Group of anomalies


@dataclass
class TemporalCycle:
    """A detected temporal cycle pattern."""

    cycle_id: str
    pattern: PatternFrequency
    failure_type: FailureType

    # Timing details
    hour: int | None = None
    day_of_week: int | None = None  # 0=Monday, 6=Sunday
    day_of_month: int | None = None

    # Pattern metrics
    confidence: float = 0.0
    occurrence_count: int = 0
    avg_failures_per_cycle: float = 0.0

    # Predictions
    next_predicted: datetime | None = None
    predicted_severity: FailureSeverity = FailureSeverity.MEDIUM

    # Metadata
    first_detected: datetime = field(default_factory=datetime.utcnow)
    last_occurrence: datetime = field(default_factory=datetime.utcnow)
    agent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "pattern": self.pattern.value,
            "failure_type": self.failure_type.value,
            "hour": self.hour,
            "day_of_week": self.day_of_week,
            "day_of_month": self.day_of_month,
            "confidence": self.confidence,
            "occurrence_count": self.occurrence_count,
            "avg_failures_per_cycle": self.avg_failures_per_cycle,
            "next_predicted": (
                self.next_predicted.isoformat() if self.next_predicted else None
            ),
            "predicted_severity": self.predicted_severity.value,
            "first_detected": self.first_detected.isoformat(),
            "last_occurrence": self.last_occurrence.isoformat(),
            "agent_id": self.agent_id,
        }


@dataclass
class FailureCascade:
    """A detected failure cascade pattern."""

    cascade_id: str
    failure_sequence: list[FailureType]

    # Cascade metrics
    occurrence_count: int = 0
    confidence: float = 0.0
    avg_time_between_steps: float = 0.0  # seconds

    # Timing
    first_detected: datetime = field(default_factory=datetime.utcnow)
    last_occurrence: datetime = field(default_factory=datetime.utcnow)

    # Context
    agent_id: str | None = None
    trigger_conditions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cascade_id": self.cascade_id,
            "failure_sequence": [f.value for f in self.failure_sequence],
            "occurrence_count": self.occurrence_count,
            "confidence": self.confidence,
            "avg_time_between_steps": self.avg_time_between_steps,
            "first_detected": self.first_detected.isoformat(),
            "last_occurrence": self.last_occurrence.isoformat(),
            "agent_id": self.agent_id,
            "trigger_conditions": self.trigger_conditions,
        }


@dataclass
class Anomaly:
    """A detected anomaly."""

    anomaly_id: str
    anomaly_type: AnomalyType
    metric_name: str

    # Values
    expected_value: float
    actual_value: float
    deviation_pct: float

    # Context
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_id: str | None = None
    failure_type: FailureType | None = None

    # Severity
    severity: FailureSeverity = FailureSeverity.MEDIUM
    requires_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_type": self.anomaly_type.value,
            "metric_name": self.metric_name,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "deviation_pct": self.deviation_pct,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "failure_type": self.failure_type.value if self.failure_type else None,
            "severity": self.severity.value,
            "requires_action": self.requires_action,
        }


@dataclass
class Prediction:
    """A prediction of future failures."""

    prediction_id: str
    failure_type: FailureType
    predicted_time: datetime

    # Confidence
    confidence: float = 0.0
    based_on_pattern: str  # cycle_id or cascade_id

    # Context
    agent_id: str | None = None
    predicted_severity: FailureSeverity = FailureSeverity.MEDIUM
    recommended_actions: list[str] = field(default_factory=list)

    # Tracking
    created_at: datetime = field(default_factory=datetime.utcnow)
    verified: bool | None = None
    verified_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "prediction_id": self.prediction_id,
            "failure_type": self.failure_type.value,
            "predicted_time": self.predicted_time.isoformat(),
            "confidence": self.confidence,
            "based_on_pattern": self.based_on_pattern,
            "agent_id": self.agent_id,
            "predicted_severity": self.predicted_severity.value,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at.isoformat(),
            "verified": self.verified,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


# ============================================================================
# TEMPORAL ANALYZER
# ============================================================================


class TemporalAnalyzer:
    """
    Detects time-based patterns in failures and successes.

    This class analyzes temporal data to find cycles, cascades,
    and anomalies that enable proactive improvements.
    """

    # Detection thresholds
    MIN_OCCURRENCES_FOR_CYCLE = 3
    CYCLE_CONFIDENCE_THRESHOLD = 0.6
    ANOMALY_STD_THRESHOLD = 2.0  # Standard deviations
    CASCADE_MIN_LENGTH = 2
    CASCADE_MAX_GAP_SECONDS = 300  # 5 minutes

    def __init__(self, knowledge_graph=None):
        """
        Initialize the temporal analyzer.

        Args:
            knowledge_graph: Optional knowledge graph for pattern storage
        """
        self.knowledge_graph = knowledge_graph

        # Pattern storage
        self._cycles: dict[str, TemporalCycle] = {}
        self._cascades: dict[str, FailureCascade] = {}
        self._anomalies: list[Anomaly] = []
        self._predictions: dict[str, Prediction] = {}

        # Time series data
        self._failure_events: list[dict[str, Any]] = []
        self._hourly_buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self._daily_buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)

        # Baseline metrics
        self._baselines: dict[str, dict[str, float]] = {}

        # Rolling windows
        self._rolling_window_size = 100
        self._rolling_metrics: dict[str, list[float]] = defaultdict(list)

    # ========================================================================
    # DATA INGESTION
    # ========================================================================

    async def record_failure(
        self,
        failure_type: FailureType,
        timestamp: datetime | None = None,
        agent_id: str | None = None,
        severity: FailureSeverity = FailureSeverity.MEDIUM,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a failure event for temporal analysis.

        Args:
            failure_type: Type of failure
            timestamp: When the failure occurred
            agent_id: Optional agent ID
            severity: Failure severity
            context: Optional context
        """
        timestamp = timestamp or datetime.now(UTC)

        event = {
            "failure_type": failure_type,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "severity": severity,
            "context": context or {},
        }

        self._failure_events.append(event)

        # Bucket by hour and day
        hour = timestamp.hour
        day_of_week = timestamp.weekday()

        self._hourly_buckets[hour].append(event)
        self._daily_buckets[day_of_week].append(event)

        # Update rolling metrics
        metric_key = f"{agent_id or 'global'}:{failure_type.value}"
        self._rolling_metrics[metric_key].append(timestamp.timestamp())

        # Trim rolling window
        if len(self._rolling_metrics[metric_key]) > self._rolling_window_size:
            self._rolling_metrics[metric_key] = self._rolling_metrics[metric_key][
                -self._rolling_window_size :
            ]

        # Check for anomalies
        await self._check_for_anomaly(event)

        # Check for cascade patterns
        await self._check_for_cascade(event)

    # ========================================================================
    # CYCLE DETECTION
    # ========================================================================

    async def detect_failure_cycles(
        self,
        agent_id: str | None = None,
        lookback_days: int = 30,
    ) -> list[TemporalCycle]:
        """
        Detect recurring failure patterns.

        Args:
            agent_id: Optional agent ID filter
            lookback_days: Days to look back

        Returns:
            List of detected temporal cycles
        """
        cycles = []
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)

        # Filter events
        events = [
            e
            for e in self._failure_events
            if e["timestamp"] >= cutoff
            and (agent_id is None or e["agent_id"] == agent_id)
        ]

        if len(events) < self.MIN_OCCURRENCES_FOR_CYCLE:
            return cycles

        # Group by failure type
        by_failure_type: dict[FailureType, list[dict]] = defaultdict(list)
        for event in events:
            by_failure_type[event["failure_type"]].append(event)

        # Detect hourly patterns
        for failure_type, type_events in by_failure_type.items():
            hourly_cycle = await self._detect_hourly_pattern(
                failure_type, type_events, agent_id
            )
            if hourly_cycle:
                cycles.append(hourly_cycle)
                self._cycles[hourly_cycle.cycle_id] = hourly_cycle

            # Detect weekly patterns
            weekly_cycle = await self._detect_weekly_pattern(
                failure_type, type_events, agent_id
            )
            if weekly_cycle:
                cycles.append(weekly_cycle)
                self._cycles[weekly_cycle.cycle_id] = weekly_cycle

        return cycles

    async def _detect_hourly_pattern(
        self,
        failure_type: FailureType,
        events: list[dict],
        agent_id: str | None,
    ) -> TemporalCycle | None:
        """Detect hourly patterns for a failure type."""
        # Count failures by hour
        hour_counts = defaultdict(int)
        for event in events:
            hour_counts[event["timestamp"].hour] += 1

        if not hour_counts:
            return None

        # Find peak hour
        peak_hour = max(hour_counts, key=hour_counts.get)
        peak_count = hour_counts[peak_hour]

        # Calculate expected count (uniform distribution)
        total_events = len(events)
        expected_per_hour = total_events / 24

        # Check if peak is significant
        if peak_count < self.MIN_OCCURRENCES_FOR_CYCLE:
            return None

        if peak_count < expected_per_hour * 2:  # At least 2x expected
            return None

        # Calculate confidence
        confidence = min(1.0, peak_count / (expected_per_hour * 3))

        if confidence < self.CYCLE_CONFIDENCE_THRESHOLD:
            return None

        # Create cycle
        cycle_id = f"hourly_{failure_type.value}_{peak_hour}"

        cycle = TemporalCycle(
            cycle_id=cycle_id,
            pattern=PatternFrequency.HOURLY,
            failure_type=failure_type,
            hour=peak_hour,
            confidence=confidence,
            occurrence_count=peak_count,
            avg_failures_per_cycle=peak_count,
            agent_id=agent_id,
        )

        # Predict next occurrence
        now = datetime.now(UTC)
        next_occurrence = now.replace(hour=peak_hour, minute=0, second=0, microsecond=0)
        if next_occurrence <= now:
            next_occurrence += timedelta(days=1)

        cycle.next_predicted = next_occurrence

        return cycle

    async def _detect_weekly_pattern(
        self,
        failure_type: FailureType,
        events: list[dict],
        agent_id: str | None,
    ) -> TemporalCycle | None:
        """Detect weekly patterns for a failure type."""
        # Count failures by day of week
        day_counts = defaultdict(int)
        for event in events:
            day_counts[event["timestamp"].weekday()] += 1

        if not day_counts:
            return None

        # Find peak day
        peak_day = max(day_counts, key=day_counts.get)
        peak_count = day_counts[peak_day]

        # Calculate expected count
        total_events = len(events)
        expected_per_day = total_events / 7

        # Check significance
        if peak_count < self.MIN_OCCURRENCES_FOR_CYCLE:
            return None

        if peak_count < expected_per_day * 1.5:  # At least 1.5x expected
            return None

        # Calculate confidence
        confidence = min(1.0, peak_count / (expected_per_day * 2.5))

        if confidence < self.CYCLE_CONFIDENCE_THRESHOLD:
            return None

        # Create cycle
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        cycle_id = f"weekly_{failure_type.value}_{day_names[peak_day]}"

        cycle = TemporalCycle(
            cycle_id=cycle_id,
            pattern=PatternFrequency.WEEKLY,
            failure_type=failure_type,
            day_of_week=peak_day,
            confidence=confidence,
            occurrence_count=peak_count,
            avg_failures_per_cycle=peak_count,
            agent_id=agent_id,
        )

        # Predict next occurrence
        now = datetime.now(UTC)
        days_ahead = peak_day - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7

        cycle.next_predicted = now + timedelta(days=days_ahead)

        return cycle

    # ========================================================================
    # CASCADE DETECTION
    # ========================================================================

    async def detect_cascades(
        self,
        agent_id: str | None = None,
        lookback_days: int = 7,
    ) -> list[FailureCascade]:
        """
        Detect failure cascade patterns.

        Args:
            agent_id: Optional agent ID filter
            lookback_days: Days to look back

        Returns:
            List of detected cascades
        """
        cascades = []
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)

        # Filter and sort events
        events = sorted(
            [
                e
                for e in self._failure_events
                if e["timestamp"] >= cutoff
                and (agent_id is None or e["agent_id"] == agent_id)
            ],
            key=lambda e: e["timestamp"],
        )

        if len(events) < self.CASCADE_MIN_LENGTH:
            return cascades

        # Find sequences
        sequences = await self._find_failure_sequences(events)

        for sequence, occurrences in sequences.items():
            if len(occurrences) >= 2:  # At least 2 occurrences
                cascade = FailureCascade(
                    cascade_id=f"cascade_{'-'.join(s.value for s in sequence)}",
                    failure_sequence=list(sequence),
                    occurrence_count=len(occurrences),
                    confidence=min(1.0, len(occurrences) / 5),
                    avg_time_between_steps=(
                        statistics.mean([o["time_between"] for o in occurrences])
                        if occurrences
                        else 0
                    ),
                    agent_id=agent_id,
                )

                cascades.append(cascade)
                self._cascades[cascade.cascade_id] = cascade

        return cascades

    async def _find_failure_sequences(
        self,
        events: list[dict],
    ) -> dict[tuple[FailureType, ...], list[dict]]:
        """Find failure sequences that form cascades."""
        sequences: dict[tuple[FailureType, ...], list[dict]] = defaultdict(list)

        i = 0
        while i < len(events):
            # Start a potential sequence
            current_sequence = [events[i]["failure_type"]]
            start_time = events[i]["timestamp"]

            j = i + 1
            while j < len(events):
                time_gap = (
                    events[j]["timestamp"] - events[j - 1]["timestamp"]
                ).total_seconds()

                if time_gap > self.CASCADE_MAX_GAP_SECONDS:
                    break

                current_sequence.append(events[j]["failure_type"])
                j += 1

            # Record sequence if long enough
            if len(current_sequence) >= self.CASCADE_MIN_LENGTH:
                sequence_tuple = tuple(current_sequence)
                time_between = 0
                if j > i + 1:
                    time_between = (
                        events[j - 1]["timestamp"] - events[i]["timestamp"]
                    ).total_seconds() / (len(current_sequence) - 1)

                sequences[sequence_tuple].append(
                    {
                        "start_time": start_time,
                        "time_between": time_between,
                    }
                )

            i = max(i + 1, j - 1)  # Move forward, but allow overlap

        return sequences

    async def _check_for_cascade(self, new_event: dict) -> None:
        """Check if a new event continues a cascade pattern."""
        # Look at recent events
        recent_cutoff = datetime.now(UTC) - timedelta(
            seconds=self.CASCADE_MAX_GAP_SECONDS
        )
        recent_events = [
            e for e in self._failure_events if e["timestamp"] >= recent_cutoff
        ]

        if len(recent_events) < self.CASCADE_MIN_LENGTH:
            return

        # Check against known cascades
        for cascade in self._cascades.values():
            sequence = cascade.failure_sequence
            if len(recent_events) >= len(sequence):
                # Check if recent events match the sequence
                match = True
                for i, failure_type in enumerate(sequence):
                    if (
                        recent_events[-(len(sequence) - i)]["failure_type"]
                        != failure_type
                    ):
                        match = False
                        break

                if match:
                    logger.warning(
                        f"Detected cascade pattern {cascade.cascade_id} in progress"
                    )

    # ========================================================================
    # ANOMALY DETECTION
    # ========================================================================

    async def detect_anomalies(
        self,
        metric_name: str | None = None,
        agent_id: str | None = None,
        lookback_hours: int = 24,
    ) -> list[Anomaly]:
        """
        Detect anomalies in failure patterns.

        Args:
            metric_name: Optional metric filter
            agent_id: Optional agent filter
            lookback_hours: Hours to look back

        Returns:
            List of detected anomalies
        """
        anomalies = []
        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)

        # Group events by metric (failure type)
        by_metric: dict[str, list[dict]] = defaultdict(list)

        for event in self._failure_events:
            if event["timestamp"] < cutoff:
                continue
            if agent_id and event["agent_id"] != agent_id:
                continue

            metric_key = (
                f"{event['agent_id'] or 'global'}:{event['failure_type'].value}"
            )
            by_metric[metric_key].append(event)

        for metric, events in by_metric.items():
            if metric_name and metric != metric_name:
                continue

            metric_anomalies = await self._detect_metric_anomalies(metric, events)
            anomalies.extend(metric_anomalies)

        self._anomalies.extend(anomalies)

        return anomalies

    async def _detect_metric_anomalies(
        self,
        metric: str,
        events: list[dict],
    ) -> list[Anomaly]:
        """Detect anomalies for a specific metric."""
        anomalies = []

        if len(events) < 5:  # Need enough data
            return anomalies

        # Calculate baseline
        timestamps = [e["timestamp"].timestamp() for e in events]

        # Group by hour
        hourly_counts = defaultdict(int)
        for event in events:
            hour_key = event["timestamp"].replace(minute=0, second=0, microsecond=0)
            hourly_counts[hour_key] += 1

        counts = list(hourly_counts.values())

        if len(counts) < 3:
            return anomalies

        mean = statistics.mean(counts)
        stdev = statistics.stdev(counts) if len(counts) > 1 else 0

        # Check for anomalies
        for hour, count in hourly_counts.items():
            if stdev == 0:
                continue

            z_score = (count - mean) / stdev

            if abs(z_score) > self.ANOMALY_STD_THRESHOLD:
                anomaly_type = AnomalyType.SPIKE if z_score > 0 else AnomalyType.DROP

                anomaly = Anomaly(
                    anomaly_id=f"anomaly_{metric}_{hour.isoformat()}",
                    anomaly_type=anomaly_type,
                    metric_name=metric,
                    expected_value=mean,
                    actual_value=count,
                    deviation_pct=abs(z_score) * 100,
                    timestamp=hour,
                    severity=(
                        FailureSeverity.HIGH
                        if abs(z_score) > 3
                        else FailureSeverity.MEDIUM
                    ),
                    requires_action=abs(z_score) > 2.5,
                )

                anomalies.append(anomaly)

        return anomalies

    async def _check_for_anomaly(self, new_event: dict) -> None:
        """Check if a new event is anomalous."""
        metric_key = (
            f"{new_event.get('agent_id') or 'global'}:{new_event['failure_type'].value}"
        )

        # Get recent events for this metric
        recent_cutoff = datetime.now(UTC) - timedelta(hours=1)
        recent_count = sum(
            1
            for e in self._failure_events
            if e["failure_type"] == new_event["failure_type"]
            and e["timestamp"] >= recent_cutoff
        )

        # Get baseline
        baseline = self._baselines.get(metric_key, {})
        expected_hourly = baseline.get("hourly_mean", 1.0)

        # Update baseline
        if metric_key not in self._baselines:
            self._baselines[metric_key] = {"hourly_mean": 1.0, "samples": 0}

        samples = self._baselines[metric_key]["samples"]
        old_mean = self._baselines[metric_key]["hourly_mean"]
        new_mean = (old_mean * samples + recent_count) / (samples + 1)

        self._baselines[metric_key]["hourly_mean"] = new_mean
        self._baselines[metric_key]["samples"] = samples + 1

        # Check for spike
        if recent_count > expected_hourly * 3:
            logger.warning(
                f"Anomaly detected: {metric_key} count {recent_count} "
                f"exceeds expected {expected_hourly:.1f}"
            )

    # ========================================================================
    # PREDICTIONS
    # ========================================================================

    async def predict_failures(
        self,
        agent_id: str | None = None,
        horizon_hours: int = 24,
    ) -> list[Prediction]:
        """
        Predict failures within the time horizon.

        Args:
            agent_id: Optional agent filter
            horizon_hours: Hours to predict ahead

        Returns:
            List of predictions
        """
        predictions = []
        now = datetime.now(UTC)
        horizon = now + timedelta(hours=horizon_hours)

        # Predict from cycles
        for cycle in self._cycles.values():
            if agent_id and cycle.agent_id != agent_id:
                continue

            if cycle.next_predicted and cycle.next_predicted <= horizon:
                prediction = Prediction(
                    prediction_id=f"pred_{cycle.cycle_id}_{now.isoformat()}",
                    failure_type=cycle.failure_type,
                    predicted_time=cycle.next_predicted,
                    confidence=cycle.confidence,
                    based_on_pattern=cycle.cycle_id,
                    agent_id=agent_id,
                    predicted_severity=cycle.predicted_severity,
                    recommended_actions=await self._get_preventive_actions(cycle),
                )

                predictions.append(prediction)
                self._predictions[prediction.prediction_id] = prediction

        # Sort by predicted time
        predictions.sort(key=lambda p: p.predicted_time)

        return predictions

    async def _get_preventive_actions(
        self,
        cycle: TemporalCycle,
    ) -> list[str]:
        """Get recommended preventive actions for a cycle."""
        actions = []

        # Map failure types to preventive actions
        preventive_map = {
            FailureType.RATE_LIMITED: [
                "Pre-warm rate limit tokens",
                "Enable request queuing",
                "Reduce concurrent requests",
            ],
            FailureType.TOOL_TIMEOUT: [
                "Increase timeout buffer",
                "Enable early cancellation",
                "Pre-cache common results",
            ],
            FailureType.MEMORY_EXHAUSTION: [
                "Trigger garbage collection",
                "Reduce cache sizes",
                "Enable memory pooling",
            ],
            FailureType.LLM_TIMEOUT: [
                "Switch to faster model",
                "Reduce prompt complexity",
                "Enable streaming",
            ],
        }

        actions = preventive_map.get(
            cycle.failure_type,
            [
                f"Monitor for {cycle.failure_type.value}",
                "Prepare fallback strategies",
            ],
        )

        return actions

    async def verify_prediction(
        self,
        prediction_id: str,
        occurred: bool,
    ) -> Prediction | None:
        """
        Verify if a prediction was accurate.

        Args:
            prediction_id: The prediction ID
            occurred: Whether the predicted failure occurred

        Returns:
            Updated prediction
        """
        prediction = self._predictions.get(prediction_id)
        if not prediction:
            return None

        prediction.verified = occurred
        prediction.verified_at = datetime.now(UTC)

        return prediction

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """Get temporal analyzer statistics."""
        return {
            "total_events": len(self._failure_events),
            "detected_cycles": len(self._cycles),
            "detected_cascades": len(self._cascades),
            "detected_anomalies": len(self._anomalies),
            "active_predictions": len(self._predictions),
            "metrics_tracked": len(self._baselines),
        }

    def get_cycle(self, cycle_id: str) -> TemporalCycle | None:
        """Get a cycle by ID."""
        return self._cycles.get(cycle_id)

    def get_cascade(self, cascade_id: str) -> FailureCascade | None:
        """Get a cascade by ID."""
        return self._cascades.get(cascade_id)

    def get_prediction(self, prediction_id: str) -> Prediction | None:
        """Get a prediction by ID."""
        return self._predictions.get(prediction_id)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_temporal_analyzer: TemporalAnalyzer | None = None


def get_temporal_analyzer() -> TemporalAnalyzer:
    """Get the singleton temporal analyzer instance."""
    global _temporal_analyzer
    if _temporal_analyzer is None:
        _temporal_analyzer = TemporalAnalyzer()
    return _temporal_analyzer


def initialize_temporal_analyzer(knowledge_graph=None) -> TemporalAnalyzer:
    """Initialize the temporal analyzer."""
    global _temporal_analyzer
    _temporal_analyzer = TemporalAnalyzer(knowledge_graph)
    return _temporal_analyzer
