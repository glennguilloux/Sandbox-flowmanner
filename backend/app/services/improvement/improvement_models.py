"""
Improvement Models - Database models for tracking improvement metrics
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ImprovementStatus(str, Enum):
    """Status of an improvement cycle"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ImprovementType(str, Enum):
    """Type of improvement"""

    PROMPT_OPTIMIZATION = "prompt_optimization"
    PARAMETER_TUNING = "parameter_tuning"
    TOOL_SELECTION = "tool_selection"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class ImprovementCycle:
    """Tracks an improvement cycle"""

    id: str
    improvement_type: ImprovementType
    status: ImprovementStatus = ImprovementStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    changes_applied: list[str] = field(default_factory=list)
    rollback_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementMetric:
    """A metric tracked during improvement"""

    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ImprovementInsight:
    """An insight generated from improvement analysis"""

    id: str
    category: str
    description: str
    confidence: float
    suggested_action: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    applied: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def create_improvement_cycle(cycle_id: str, improvement_type: ImprovementType) -> ImprovementCycle:
    """Create a new improvement cycle"""
    return ImprovementCycle(id=cycle_id, improvement_type=improvement_type, started_at=datetime.now(UTC))


def create_metric(name: str, value: float, tags: dict[str, str] | None = None) -> ImprovementMetric:
    """Create a new improvement metric"""
    return ImprovementMetric(name=name, value=value, tags=tags or {})


def create_insight(
    insight_id: str,
    category: str,
    description: str,
    confidence: float,
    suggested_action: str,
) -> ImprovementInsight:
    """Create a new improvement insight"""
    return ImprovementInsight(
        id=insight_id,
        category=category,
        description=description,
        confidence=confidence,
        suggested_action=suggested_action,
    )


@dataclass
class AppliedImprovement:
    """Tracks an improvement that was applied"""

    id: str
    improvement_type: ImprovementType
    description: str
    applied_at: datetime = field(default_factory=datetime.utcnow)
    applied_by: str = "system"
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    rollback_available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


def create_applied_improvement(
    improvement_id: str,
    improvement_type: ImprovementType,
    description: str,
    applied_by: str = "system",
) -> AppliedImprovement:
    """Create a new applied improvement record"""
    return AppliedImprovement(
        id=improvement_id,
        improvement_type=improvement_type,
        description=description,
        applied_by=applied_by,
    )


@dataclass
class FailureContextModel:
    """Database model for failure context"""

    id: str
    failure_type: str
    severity: str
    context_data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementSession:
    """Tracks an improvement session"""

    id: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    status: ImprovementStatus = ImprovementStatus.PENDING
    cycles: list[ImprovementCycle] = field(default_factory=list)
    metrics: list[ImprovementMetric] = field(default_factory=list)
    insights: list[ImprovementInsight] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementMetrics:
    """Aggregated improvement metrics"""

    total_cycles: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    average_improvement: float = 0.0
    total_insights: int = 0
    applied_insights: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


def create_failure_context(
    context_id: str,
    failure_type: str,
    severity: str,
    context_data: dict[str, Any] | None = None,
) -> FailureContextModel:
    """Create a new failure context record"""
    return FailureContextModel(
        id=context_id,
        failure_type=failure_type,
        severity=severity,
        context_data=context_data or {},
    )


def create_improvement_session(session_id: str) -> ImprovementSession:
    """Create a new improvement session"""
    return ImprovementSession(id=session_id)


def create_improvement_metrics() -> ImprovementMetrics:
    """Create a new improvement metrics record"""
    return ImprovementMetrics()
