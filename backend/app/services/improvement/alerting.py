"""
Alerting for Autonomous Self-Improvement System.

This module provides alerting and notification capabilities for significant
events in the improvement system, such as rollbacks, critical failures,
and oscillation detection.

Phase 5E of the Autonomous Self-Improvement Architecture.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class AlertSeverity(str, Enum):
    """Severity levels for improvement alerts."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of improvement alerts."""

    # Rollback events
    ROLLBACK_TRIGGERED = "rollback_triggered"
    ROLLBACK_FAILED = "rollback_failed"

    # Failure events
    CRITICAL_FAILURE_SPIKE = "critical_failure_spike"
    FAILURE_THRESHOLD_EXCEEDED = "failure_threshold_exceeded"

    # Oscillation events
    OSCILLATION_DETECTED = "oscillation_detected"
    OSCILLATION_RISK_HIGH = "oscillation_risk_high"

    # Improvement events
    IMPROVEMENT_APPLIED = "improvement_applied"
    IMPROVEMENT_REJECTED = "improvement_rejected"
    IMPROVEMENT_SESSION_STARTED = "improvement_session_started"
    IMPROVEMENT_SESSION_COMPLETED = "improvement_session_completed"

    # System events
    IMPROVEMENT_SYSTEM_HEALTHY = "improvement_system_healthy"
    IMPROVEMENT_SYSTEM_DEGRADED = "improvement_system_degraded"
    IMPROVEMENT_SYSTEM_ERROR = "improvement_system_error"


@dataclass
class ImprovementAlert:
    """An alert from the improvement system."""

    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_id: str | None = None
    session_id: str | None = None
    knob_name: str | None = None
    failure_type: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize alert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "knob_name": self.knob_name,
            "failure_type": self.failure_type,
            "metrics": self.metrics,
            "context": self.context,
            "acknowledged": self.acknowledged,
            "acknowledged_at": (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
            "acknowledged_by": self.acknowledged_by,
        }


# ============================================================================
# ALERT HANDLER
# ============================================================================


class ImprovementAlertHandler:
    """
    Handles alerts from the improvement system.

    This class provides alerting capabilities for significant events,
    integrating with the existing notification infrastructure.
    """

    def __init__(self, notification_service=None):
        """
        Initialize the alert handler.

        Args:
            notification_service: Optional notification service for sending alerts
        """
        self.notification_service = notification_service
        self._alert_history: list[ImprovementAlert] = []
        self._alert_callbacks: list[Callable[[ImprovementAlert], None]] = []
        self._alert_counts: dict[str, int] = defaultdict(int)
        self._rate_limit_window = timedelta(minutes=5)
        self._last_alert_time: dict[str, datetime] = {}

        # Alert thresholds
        self.thresholds = {
            "failure_spike_multiplier": 3.0,  # Alert if failures > 3x baseline
            "failure_spike_min_count": 10,  # Minimum failures to consider spike
            "oscillation_threshold": 3,  # Alert if >3 changes to same knob in 24h
            "error_rate_threshold": 0.5,  # Alert if error rate > 50%
            "latency_increase_threshold": 2.0,  # Alert if latency > 2x baseline
        }

    def register_callback(self, callback: Callable[[ImprovementAlert], None]) -> None:
        """
        Register a callback to be called when an alert is raised.

        Args:
            callback: Function to call with the alert
        """
        self._alert_callbacks.append(callback)

    async def raise_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        knob_name: str | None = None,
        failure_type: str | None = None,
        metrics: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ImprovementAlert:
        """
        Raise an alert.

        Args:
            alert_type: Type of alert
            severity: Severity level
            title: Alert title
            message: Detailed message
            agent_id: Optional agent ID
            session_id: Optional session ID
            knob_name: Optional knob name
            failure_type: Optional failure type
            metrics: Optional metrics data
            context: Optional context data

        Returns:
            The created alert
        """
        import uuid

        alert_id = str(uuid.uuid4())

        # Check rate limiting
        alert_key = f"{alert_type.value}:{agent_id or 'global'}"
        if self._is_rate_limited(alert_key):
            logger.debug("Rate limited alert: %s", alert_key)
            # Still create the alert but don't send notifications
            alert = ImprovementAlert(
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                agent_id=agent_id,
                session_id=session_id,
                knob_name=knob_name,
                failure_type=failure_type,
                metrics=metrics or {},
                context=context or {},
            )
            self._alert_history.append(alert)
            return alert

        alert = ImprovementAlert(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            agent_id=agent_id,
            session_id=session_id,
            knob_name=knob_name,
            failure_type=failure_type,
            metrics=metrics or {},
            context=context or {},
        )

        # Store in history
        self._alert_history.append(alert)
        self._last_alert_time[alert_key] = datetime.now(UTC)
        self._alert_counts[alert_key] += 1

        # Log the alert
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.ERROR: logging.ERROR,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }.get(severity, logging.INFO)

        logger.log(log_level, f"[{alert_type.value}] {title}: {message}")

        # Call registered callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.warning("Alert callback failed: %s", e)

        # Send to notification service if available
        if self.notification_service:
            await self._send_notification(alert)

        return alert

    async def alert_rollback_triggered(
        self,
        knob_name: str,
        reason: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> ImprovementAlert:
        """
        Alert that a rollback was triggered.

        Args:
            knob_name: Name of the knob that was rolled back
            reason: Reason for the rollback
            agent_id: Optional agent ID
            session_id: Optional session ID
            metrics: Optional metrics that triggered the rollback

        Returns:
            The created alert
        """
        return await self.raise_alert(
            alert_type=AlertType.ROLLBACK_TRIGGERED,
            severity=AlertSeverity.WARNING,
            title=f"Knob Rollback Triggered: {knob_name}",
            message=f"Knob '{knob_name}' was rolled back. Reason: {reason}",
            agent_id=agent_id,
            session_id=session_id,
            knob_name=knob_name,
            metrics=metrics,
            context={"reason": reason},
        )

    async def alert_rollback_failed(
        self,
        knob_name: str,
        error: str,
        agent_id: str | None = None,
    ) -> ImprovementAlert:
        """
        Alert that a rollback failed.

        Args:
            knob_name: Name of the knob
            error: Error message
            agent_id: Optional agent ID

        Returns:
            The created alert
        """
        return await self.raise_alert(
            alert_type=AlertType.ROLLBACK_FAILED,
            severity=AlertSeverity.ERROR,
            title=f"Rollback Failed: {knob_name}",
            message=f"Failed to rollback knob '{knob_name}': {error}",
            agent_id=agent_id,
            knob_name=knob_name,
            context={"error": error},
        )

    async def alert_failure_spike(
        self,
        failure_type: str,
        current_count: int,
        baseline_count: int,
        agent_id: str | None = None,
    ) -> ImprovementAlert:
        """
        Alert on a spike in failures.

        Args:
            failure_type: Type of failure
            current_count: Current failure count
            baseline_count: Baseline failure count
            agent_id: Optional agent ID

        Returns:
            The created alert
        """
        multiplier = (
            current_count / baseline_count if baseline_count > 0 else float("inf")
        )

        return await self.raise_alert(
            alert_type=AlertType.CRITICAL_FAILURE_SPIKE,
            severity=AlertSeverity.CRITICAL,
            title=f"Failure Spike Detected: {failure_type}",
            message=f"Failure type '{failure_type}' spiked to {current_count} ({multiplier:.1f}x baseline of {baseline_count})",
            agent_id=agent_id,
            failure_type=failure_type,
            metrics={
                "current_count": current_count,
                "baseline_count": baseline_count,
                "multiplier": multiplier,
            },
        )

    async def alert_oscillation_detected(
        self,
        knob_name: str,
        change_count: int,
        time_window_hours: float,
        agent_id: str | None = None,
    ) -> ImprovementAlert:
        """
        Alert that oscillation was detected.

        Args:
            knob_name: Name of the oscillating knob
            change_count: Number of changes in the time window
            time_window_hours: Time window in hours
            agent_id: Optional agent ID

        Returns:
            The created alert
        """
        return await self.raise_alert(
            alert_type=AlertType.OSCILLATION_DETECTED,
            severity=AlertSeverity.ERROR,
            title=f"Oscillation Detected: {knob_name}",
            message=f"Knob '{knob_name}' was changed {change_count} times in {time_window_hours:.1f} hours, indicating oscillation",
            agent_id=agent_id,
            knob_name=knob_name,
            metrics={
                "change_count": change_count,
                "time_window_hours": time_window_hours,
            },
        )

    async def alert_improvement_applied(
        self,
        strategy_type: str,
        knob_name: str,
        improvement_delta: float,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> ImprovementAlert:
        """
        Alert that an improvement was successfully applied.

        Args:
            strategy_type: Type of strategy applied
            knob_name: Name of the knob that was adjusted
            improvement_delta: Measured improvement
            agent_id: Optional agent ID
            session_id: Optional session ID

        Returns:
            The created alert
        """
        return await self.raise_alert(
            alert_type=AlertType.IMPROVEMENT_APPLIED,
            severity=AlertSeverity.INFO,
            title=f"Improvement Applied: {strategy_type}",
            message=f"Strategy '{strategy_type}' applied to knob '{knob_name}', resulting in {improvement_delta:.1%} improvement",
            agent_id=agent_id,
            session_id=session_id,
            knob_name=knob_name,
            metrics={"improvement_delta": improvement_delta},
        )

    async def alert_improvement_rejected(
        self,
        strategy_type: str,
        reason: str,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> ImprovementAlert:
        """
        Alert that an improvement was rejected.

        Args:
            strategy_type: Type of strategy that was rejected
            reason: Reason for rejection
            agent_id: Optional agent ID
            session_id: Optional session ID

        Returns:
            The created alert
        """
        return await self.raise_alert(
            alert_type=AlertType.IMPROVEMENT_REJECTED,
            severity=AlertSeverity.WARNING,
            title=f"Improvement Rejected: {strategy_type}",
            message=f"Strategy '{strategy_type}' was rejected. Reason: {reason}",
            agent_id=agent_id,
            session_id=session_id,
            context={"reason": reason},
        )

    async def alert_session_completed(
        self,
        session_id: str,
        success: bool,
        improvement_delta: float | None,
        agent_id: str | None = None,
    ) -> ImprovementAlert:
        """
        Alert that an improvement session completed.

        Args:
            session_id: The session ID
            success: Whether the session was successful
            improvement_delta: The improvement delta (if any)
            agent_id: Optional agent ID

        Returns:
            The created alert
        """
        severity = AlertSeverity.INFO if success else AlertSeverity.WARNING
        title = (
            "Improvement Session Completed" if success else "Improvement Session Failed"
        )
        message = f"Session {session_id} completed."
        if improvement_delta is not None:
            message += f" Improvement: {improvement_delta:.1%}"

        return await self.raise_alert(
            alert_type=AlertType.IMPROVEMENT_SESSION_COMPLETED,
            severity=severity,
            title=title,
            message=message,
            agent_id=agent_id,
            session_id=session_id,
            metrics=(
                {"improvement_delta": improvement_delta} if improvement_delta else {}
            ),
        )

    def get_recent_alerts(
        self,
        limit: int = 50,
        severity: AlertSeverity | None = None,
        alert_type: AlertType | None = None,
        agent_id: str | None = None,
        unacknowledged_only: bool = False,
    ) -> list[ImprovementAlert]:
        """
        Get recent alerts.

        Args:
            limit: Maximum number of alerts to return
            severity: Optional severity filter
            alert_type: Optional alert type filter
            agent_id: Optional agent ID filter
            unacknowledged_only: Only return unacknowledged alerts

        Returns:
            List of matching alerts
        """
        alerts = self._alert_history

        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        if agent_id:
            alerts = [a for a in alerts if a.agent_id == agent_id]
        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        # Sort by timestamp descending
        alerts = sorted(alerts, key=lambda a: a.timestamp, reverse=True)

        return alerts[:limit]

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str | None = None,
    ) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: The alert ID
            acknowledged_by: Who acknowledged the alert

        Returns:
            True if successful, False if not found
        """
        for alert in self._alert_history:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now(UTC)
                alert.acknowledged_by = acknowledged_by
                return True
        return False

    def clear_old_alerts(self, older_than: timedelta = timedelta(days=7)) -> int:
        """
        Clear alerts older than the specified age.

        Args:
            older_than: Age threshold

        Returns:
            Number of alerts cleared
        """
        cutoff = datetime.now(UTC) - older_than
        original_count = len(self._alert_history)
        self._alert_history = [a for a in self._alert_history if a.timestamp >= cutoff]
        return original_count - len(self._alert_history)

    def _is_rate_limited(self, alert_key: str) -> bool:
        """Check if an alert key is rate limited."""
        if alert_key not in self._last_alert_time:
            return False

        last_time = self._last_alert_time[alert_key]
        return (datetime.now(UTC) - last_time) < self._rate_limit_window

    async def _send_notification(self, alert: ImprovementAlert) -> None:
        """Send notification through the notification service."""
        if not self.notification_service:
            return

        try:
            # Try different notification methods
            if hasattr(self.notification_service, "send_alert"):
                await self.notification_service.send_alert(
                    title=alert.title,
                    message=alert.message,
                    severity=alert.severity.value,
                    data=alert.to_dict(),
                )
            elif hasattr(self.notification_service, "notify"):
                await self.notification_service.notify(
                    title=alert.title,
                    message=alert.message,
                    level=alert.severity.value,
                )
            else:
                logger.debug(
                    "No compatible notification method found for alert: %s",
                    alert.alert_id,
                )

        except Exception as e:
            logger.warning("Failed to send notification: %s", e)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_alert_handler: ImprovementAlertHandler | None = None


def get_alert_handler() -> ImprovementAlertHandler:
    """Get the singleton alert handler instance."""
    global _alert_handler
    if _alert_handler is None:
        _alert_handler = ImprovementAlertHandler()
    return _alert_handler


def initialize_alert_handler(notification_service=None) -> ImprovementAlertHandler:
    """Initialize the alert handler with a notification service."""
    global _alert_handler
    _alert_handler = ImprovementAlertHandler(notification_service)
    return _alert_handler


# Alias for backward compatibility
Alert = ImprovementAlert


class AlertingSystem:
    """System for managing and dispatching alerts"""

    def __init__(self):
        self.alerts: list[ImprovementAlert] = []
        self.handlers: list[Callable] = []

    def add_alert(self, alert: ImprovementAlert) -> None:
        """Add an alert to the system"""
        self.alerts.append(alert)
        for handler in self.handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error("Alert handler error: %s", e)

    def register_handler(self, handler: Callable) -> None:
        """Register an alert handler"""
        self.handlers.append(handler)

    def get_alerts(self, limit: int = 100) -> list[ImprovementAlert]:
        """Get recent alerts"""
        return self.alerts[-limit:]

    def clear_alerts(self) -> None:
        """Clear all alerts"""
        self.alerts.clear()


_alerting_system: AlertingSystem | None = None


def get_alerting_system() -> AlertingSystem:
    """Get the singleton alerting system instance"""
    global _alerting_system
    if _alerting_system is None:
        _alerting_system = AlertingSystem()
    return _alerting_system
