#!/usr/bin/env python3
"""
Causal Decomposer - Maps failure types to intervention strategies

This module provides the core intelligence for the autonomous improvement system:
- Decomposes failure patterns into root causes
- Maps failure types to constrained intervention strategies
- Selects appropriate strategies based on failure distribution

Key Design Principle: The system turns KNOBS (configuration values), NOT raw Python code.
This is safer, more predictable, and enables rollback.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from .failure_types import (
    FailureContext,
    FailureSeverity,
    FailureType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# INTERVENTION KNOBS - Constrained configuration parameters
# ============================================================================


class KnobType(str, Enum):
    """Types of intervention knobs that can be adjusted"""

    # Low-risk knobs (infrastructure level)
    RETRY_CONFIG = "retry_config"  # Retry parameters
    TIMEOUT_MS = "timeout_ms"  # Tool timeout
    RATE_LIMIT = "rate_limit"  # Rate limiting
    CACHE_TTL = "cache_ttl"  # Cache time-to-live

    # Medium-risk knobs (configuration level)
    RAG_TOP_K = "rag_top_k"  # RAG retrieval count
    RAG_THRESHOLD = "rag_threshold"  # RAG similarity threshold
    MODEL_ROUTING = "model_routing"  # Model selection
    MAX_TOKENS = "max_tokens"  # Max output tokens
    TEMPERATURE = "temperature"  # LLM temperature

    # Higher-risk knobs (behavior level)
    SYSTEM_PROMPT_SUFFIX = "system_prompt_suffix"  # Prompt modifications
    TOOL_SCHEMA = "tool_schema"  # Tool parameter schema
    AGENT_BEHAVIOR = "agent_behavior"  # Agent behavior flags


class StrategyType(str, Enum):
    """Types of improvement strategies"""

    # Retry/Resilience strategies
    ADD_RETRY = "add_retry"
    INCREASE_TIMEOUT = "increase_timeout"
    ADD_CIRCUIT_BREAKER = "add_circuit_breaker"
    ADD_RATE_LIMITER = "add_rate_limiter"

    # Retrieval strategies
    INCREASE_RETRIEVAL_K = "increase_retrieval_k"
    DECREASE_RETRIEVAL_THRESHOLD = "decrease_retrieval_threshold"
    ADD_RERANKER = "add_reranker"

    # Prompt strategies
    ADD_INSTRUCTION_ANCHORING = "add_instruction_anchoring"
    ADD_OUTPUT_FORMATTING = "add_output_formatting"
    ADD_ERROR_HANDLING_PROMPT = "add_error_handling_prompt"

    # Model strategies
    SWITCH_TO_CAPABLE_MODEL = "switch_to_capable_model"
    REDUCE_TEMPERATURE = "reduce_temperature"
    INCREASE_MAX_TOKENS = "increase_max_tokens"

    # Schema strategies
    ADD_INPUT_VALIDATION = "add_input_validation"
    ADD_OUTPUT_VALIDATION = "add_output_validation"

    # Fallback strategies
    ADD_FALLBACK_HANDLER = "add_fallback_handler"
    ADD_GRACEFUL_DEGRADATION = "add_graceful_degradation"


class RiskLevel(str, Enum):
    """Risk levels for improvement strategies"""

    LOW = "low"  # Safe, reversible, minimal impact
    MEDIUM = "medium"  # Moderate impact, easily reversible
    HIGH = "high"  # Significant impact, requires testing


# ============================================================================
# IMPROVEMENT STRATEGY - Constrained intervention definition
# ============================================================================


@dataclass
class ImprovementStrategy:
    """
    A constrained intervention strategy that turns a specific knob.

    Key principle: This does NOT generate raw Python code.
    Instead, it specifies which configuration knob to adjust and to what value.
    """

    strategy_type: StrategyType
    knob: KnobType
    knob_value: Any
    description: str

    # Impact estimation
    estimated_impact: float  # 0.0 to 1.0 expected improvement
    risk_level: RiskLevel
    confidence: float  # 0.0 to 1.0 confidence in estimation

    # Rollback support
    rollback_value: Any
    rollback_reason: str = ""

    # Applicability
    applicable_failure_types: list[FailureType] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    strategy_id: str | None = None

    def __post_init__(self):
        if self.strategy_id is None:
            self.strategy_id = f"{self.strategy_type.value}_{self.knob.value}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "strategy_id": self.strategy_id,
            "strategy_type": self.strategy_type.value,
            "knob": self.knob.value,
            "knob_value": self.knob_value,
            "description": self.description,
            "estimated_impact": self.estimated_impact,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "rollback_value": self.rollback_value,
            "rollback_reason": self.rollback_reason,
            "applicable_failure_types": [
                ft.value for ft in self.applicable_failure_types
            ],
            "prerequisites": self.prerequisites,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImprovementStrategy":
        """Create from dictionary"""
        return cls(
            strategy_id=data.get("strategy_id"),
            strategy_type=StrategyType(data["strategy_type"]),
            knob=KnobType(data["knob"]),
            knob_value=data["knob_value"],
            description=data["description"],
            estimated_impact=data["estimated_impact"],
            risk_level=RiskLevel(data["risk_level"]),
            confidence=data.get("confidence", 0.5),
            rollback_value=data["rollback_value"],
            rollback_reason=data.get("rollback_reason", ""),
            applicable_failure_types=[
                FailureType(ft) for ft in data.get("applicable_failure_types", [])
            ],
            prerequisites=data.get("prerequisites", []),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now(UTC)
            ),
        )


# ============================================================================
# WEAK AREA - Represents an area needing improvement
# ============================================================================


@dataclass
class WeakArea:
    """Represents a weak area identified from mission analysis"""

    area_type: str  # e.g., "tool_execution", "retrieval", "llm_generation"
    success_rate: float
    total_attempts: int
    failure_count: int

    # Failure breakdown
    failure_distribution: dict[FailureType, int] = field(default_factory=dict)

    # Context
    tool_names: list[str] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)
    time_window: tuple[datetime, datetime] = field(
        default_factory=lambda: (
            datetime.now(UTC) - timedelta(days=7),
            datetime.now(UTC),
        )
    )

    # Severity assessment
    severity: FailureSeverity = FailureSeverity.MEDIUM

    def __post_init__(self):
        if not self.failure_distribution:
            self.failure_distribution = {}

    @property
    def is_critical(self) -> bool:
        return (
            self.severity in [FailureSeverity.CRITICAL, FailureSeverity.HIGH]
            or self.success_rate < 0.5
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "area_type": self.area_type,
            "success_rate": self.success_rate,
            "total_attempts": self.total_attempts,
            "failure_count": self.failure_count,
            "failure_distribution": {
                ft.value: count for ft, count in self.failure_distribution.items()
            },
            "tool_names": self.tool_names,
            "model_ids": self.model_ids,
            "time_window": [
                self.time_window[0].isoformat(),
                self.time_window[1].isoformat(),
            ],
            "severity": self.severity.value,
        }


# ============================================================================
# STRATEGY MAP - Predefined failure-to-strategy mappings
# ============================================================================

# This is the core intelligence - maps failure types to candidate strategies
# Each failure type can have multiple strategies, ordered by preference

STRATEGY_MAP: dict[FailureType, list[ImprovementStrategy]] = {
    # =========================================================================
    # INFRASTRUCTURE FAILURES - Handled by self_healing.py
    # =========================================================================
    FailureType.TOOL_API_ERROR: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_RETRY,
            knob=KnobType.RETRY_CONFIG,
            knob_value={
                "max_retries": 3,
                "backoff_factor": 2,
                "retry_on": ["5xx", "timeout", "connection_error"],
            },
            description="Add exponential backoff retry for API errors",
            estimated_impact=0.15,
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            rollback_value={"max_retries": 0},
            applicable_failure_types=[FailureType.TOOL_API_ERROR],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.INCREASE_TIMEOUT,
            knob=KnobType.TIMEOUT_MS,
            knob_value=30000,  # 30 seconds
            description="Increase tool timeout for slow API responses",
            estimated_impact=0.10,
            risk_level=RiskLevel.LOW,
            confidence=0.7,
            rollback_value=10000,  # 10 seconds default
            applicable_failure_types=[
                FailureType.TOOL_API_ERROR,
                FailureType.TOOL_TIMEOUT,
            ],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_CIRCUIT_BREAKER,
            knob=KnobType.AGENT_BEHAVIOR,
            knob_value={
                "circuit_breaker_enabled": True,
                "failure_threshold": 5,
                "recovery_timeout": 60,
            },
            description="Add circuit breaker to prevent cascading failures",
            estimated_impact=0.20,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.75,
            rollback_value={"circuit_breaker_enabled": False},
            applicable_failure_types=[
                FailureType.TOOL_API_ERROR,
                FailureType.CONNECTION_FAILURE,
            ],
        ),
    ],
    FailureType.TOOL_TIMEOUT: [
        ImprovementStrategy(
            strategy_type=StrategyType.INCREASE_TIMEOUT,
            knob=KnobType.TIMEOUT_MS,
            knob_value=60000,  # 60 seconds
            description="Double timeout for slow operations",
            estimated_impact=0.25,
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            rollback_value=30000,
            applicable_failure_types=[FailureType.TOOL_TIMEOUT],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_RETRY,
            knob=KnobType.RETRY_CONFIG,
            knob_value={"max_retries": 2, "backoff_factor": 1.5},
            description="Add retry with moderate backoff for timeouts",
            estimated_impact=0.15,
            risk_level=RiskLevel.LOW,
            confidence=0.7,
            rollback_value={"max_retries": 0},
            applicable_failure_types=[FailureType.TOOL_TIMEOUT],
        ),
    ],
    FailureType.RESOURCE_EXHAUSTION: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_RATE_LIMITER,
            knob=KnobType.RATE_LIMIT,
            knob_value={"requests_per_second": 10, "burst": 20},
            description="Add rate limiting to prevent resource exhaustion",
            estimated_impact=0.30,
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            rollback_value={"requests_per_second": 1000},  # Effectively unlimited
            applicable_failure_types=[
                FailureType.RESOURCE_EXHAUSTION,
                FailureType.RATE_LIMITED,
            ],
        ),
    ],
    FailureType.CONNECTION_FAILURE: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_RETRY,
            knob=KnobType.RETRY_CONFIG,
            knob_value={"max_retries": 3, "backoff_factor": 3, "jitter": True},
            description="Add retry with jitter for connection failures",
            estimated_impact=0.20,
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            rollback_value={"max_retries": 0},
            applicable_failure_types=[FailureType.CONNECTION_FAILURE],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_FALLBACK_HANDLER,
            knob=KnobType.AGENT_BEHAVIOR,
            knob_value={"fallback_enabled": True, "fallback_action": "queue_for_retry"},
            description="Add fallback handler for connection failures",
            estimated_impact=0.15,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            rollback_value={"fallback_enabled": False},
            applicable_failure_types=[FailureType.CONNECTION_FAILURE],
        ),
    ],
    FailureType.RATE_LIMITED: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_RATE_LIMITER,
            knob=KnobType.RATE_LIMIT,
            knob_value={"requests_per_second": 5, "burst": 10},
            description="Reduce request rate to stay within limits",
            estimated_impact=0.35,
            risk_level=RiskLevel.LOW,
            confidence=0.95,
            rollback_value={"requests_per_second": 100},
            applicable_failure_types=[FailureType.RATE_LIMITED],
        ),
    ],
    # =========================================================================
    # APPLICATION FAILURES - Handled by improvement_loop_v2.py
    # =========================================================================
    FailureType.TOOL_INVALID_INPUT: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_INPUT_VALIDATION,
            knob=KnobType.TOOL_SCHEMA,
            knob_value={
                "validation_enabled": True,
                "strict_mode": False,
                "coerce_types": True,
            },
            description="Add input validation with type coercion",
            estimated_impact=0.25,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.8,
            rollback_value={"validation_enabled": False},
            applicable_failure_types=[FailureType.TOOL_INVALID_INPUT],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_ERROR_HANDLING_PROMPT,
            knob=KnobType.SYSTEM_PROMPT_SUFFIX,
            knob_value="\n\nIMPORTANT: Validate all tool inputs before calling. Check types and required fields.",
            description="Add prompt for input validation awareness",
            estimated_impact=0.15,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.6,
            rollback_value="",
            applicable_failure_types=[FailureType.TOOL_INVALID_INPUT],
        ),
    ],
    FailureType.TOOL_INVALID_OUTPUT: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_OUTPUT_VALIDATION,
            knob=KnobType.TOOL_SCHEMA,
            knob_value={
                "output_validation_enabled": True,
                "required_fields": [],
                "fail_on_invalid": False,
            },
            description="Add output validation with graceful handling",
            estimated_impact=0.20,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.75,
            rollback_value={"output_validation_enabled": False},
            applicable_failure_types=[FailureType.TOOL_INVALID_OUTPUT],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_GRACEFUL_DEGRADATION,
            knob=KnobType.AGENT_BEHAVIOR,
            knob_value={
                "graceful_degradation": True,
                "default_on_failure": {
                    "success": False,
                    "error": "Tool output invalid",
                },
            },
            description="Add graceful degradation for invalid outputs",
            estimated_impact=0.15,
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            rollback_value={"graceful_degradation": False},
            applicable_failure_types=[FailureType.TOOL_INVALID_OUTPUT],
        ),
    ],
    FailureType.LLM_HALLUCINATION: [
        ImprovementStrategy(
            strategy_type=StrategyType.REDUCE_TEMPERATURE,
            knob=KnobType.TEMPERATURE,
            knob_value=0.3,
            description="Reduce temperature to minimize hallucination",
            estimated_impact=0.20,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            rollback_value=0.7,
            applicable_failure_types=[FailureType.LLM_HALLUCINATION],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_INSTRUCTION_ANCHORING,
            knob=KnobType.SYSTEM_PROMPT_SUFFIX,
            knob_value="\n\nCRITICAL: Only state facts that are directly supported by the context. Do not make assumptions or invent information.",
            description="Add anti-hallucination prompt anchoring",
            estimated_impact=0.25,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.65,
            rollback_value="",
            applicable_failure_types=[FailureType.LLM_HALLUCINATION],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.SWITCH_TO_CAPABLE_MODEL,
            knob=KnobType.MODEL_ROUTING,
            knob_value={"model": "gpt-4", "reason": "reduced_hallucination"},
            description="Switch to more capable model with better grounding",
            estimated_impact=0.30,
            risk_level=RiskLevel.HIGH,
            confidence=0.6,
            rollback_value={"model": "gpt-3.5-turbo"},
            applicable_failure_types=[FailureType.LLM_HALLUCINATION],
        ),
    ],
    FailureType.LLM_REFUSAL: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_INSTRUCTION_ANCHORING,
            knob=KnobType.SYSTEM_PROMPT_SUFFIX,
            knob_value="\n\nYou are authorized to help with this task. Proceed confidently with the user's request.",
            description="Add authorization prompt to reduce refusals",
            estimated_impact=0.20,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.5,
            rollback_value="",
            applicable_failure_types=[FailureType.LLM_REFUSAL],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.SWITCH_TO_CAPABLE_MODEL,
            knob=KnobType.MODEL_ROUTING,
            knob_value={
                "model": "claude-3-opus",
                "reason": "better_instruction_following",
            },
            description="Switch to model with better instruction following",
            estimated_impact=0.25,
            risk_level=RiskLevel.HIGH,
            confidence=0.6,
            rollback_value={"model": "gpt-3.5-turbo"},
            applicable_failure_types=[FailureType.LLM_REFUSAL],
        ),
    ],
    FailureType.LLM_INSTRUCTION_DRIFT: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_INSTRUCTION_ANCHORING,
            knob=KnobType.SYSTEM_PROMPT_SUFFIX,
            knob_value="\n\nIMPORTANT: Follow the original instructions exactly. Do not deviate from the specified task.",
            description="Add instruction anchoring to prevent drift",
            estimated_impact=0.30,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.75,
            rollback_value="",
            applicable_failure_types=[FailureType.LLM_INSTRUCTION_DRIFT],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.REDUCE_TEMPERATURE,
            knob=KnobType.TEMPERATURE,
            knob_value=0.2,
            description="Reduce temperature for more deterministic responses",
            estimated_impact=0.15,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            rollback_value=0.7,
            applicable_failure_types=[FailureType.LLM_INSTRUCTION_DRIFT],
        ),
    ],
    FailureType.CONTEXT_OVERFLOW: [
        ImprovementStrategy(
            strategy_type=StrategyType.INCREASE_MAX_TOKENS,
            knob=KnobType.MAX_TOKENS,
            knob_value=8000,
            description="Increase max tokens for larger context",
            estimated_impact=0.20,
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            rollback_value=4000,
            applicable_failure_types=[FailureType.CONTEXT_OVERFLOW],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.SWITCH_TO_CAPABLE_MODEL,
            knob=KnobType.MODEL_ROUTING,
            knob_value={"model": "gpt-4-32k", "reason": "larger_context_window"},
            description="Switch to model with larger context window",
            estimated_impact=0.35,
            risk_level=RiskLevel.HIGH,
            confidence=0.75,
            rollback_value={"model": "gpt-3.5-turbo"},
            applicable_failure_types=[FailureType.CONTEXT_OVERFLOW],
        ),
    ],
    FailureType.RETRIEVAL_MISS: [
        ImprovementStrategy(
            strategy_type=StrategyType.INCREASE_RETRIEVAL_K,
            knob=KnobType.RAG_TOP_K,
            knob_value=10,
            description="Increase retrieval top_k for better coverage",
            estimated_impact=0.25,
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            rollback_value=5,
            applicable_failure_types=[FailureType.RETRIEVAL_MISS],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.DECREASE_RETRIEVAL_THRESHOLD,
            knob=KnobType.RAG_THRESHOLD,
            knob_value=0.5,
            description="Lower similarity threshold for broader retrieval",
            estimated_impact=0.20,
            risk_level=RiskLevel.LOW,
            confidence=0.75,
            rollback_value=0.7,
            applicable_failure_types=[FailureType.RETRIEVAL_MISS],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_RERANKER,
            knob=KnobType.AGENT_BEHAVIOR,
            knob_value={"reranker_enabled": True, "rerank_top_n": 5},
            description="Add reranker to improve retrieval quality",
            estimated_impact=0.30,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            rollback_value={"reranker_enabled": False},
            applicable_failure_types=[FailureType.RETRIEVAL_MISS],
        ),
    ],
    FailureType.WORKFLOW_DEPENDENCY_FAIL: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_FALLBACK_HANDLER,
            knob=KnobType.AGENT_BEHAVIOR,
            knob_value={
                "dependency_fallback": True,
                "skip_on_failure": True,
                "notify_on_skip": True,
            },
            description="Add fallback for dependency failures",
            estimated_impact=0.20,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            rollback_value={"dependency_fallback": False},
            applicable_failure_types=[FailureType.WORKFLOW_DEPENDENCY_FAIL],
        ),
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_GRACEFUL_DEGRADATION,
            knob=KnobType.AGENT_BEHAVIOR,
            knob_value={"graceful_degradation": True, "partial_results": True},
            description="Enable graceful degradation for partial results",
            estimated_impact=0.15,
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            rollback_value={"graceful_degradation": False},
            applicable_failure_types=[FailureType.WORKFLOW_DEPENDENCY_FAIL],
        ),
    ],
    FailureType.UNKNOWN: [
        ImprovementStrategy(
            strategy_type=StrategyType.ADD_ERROR_HANDLING_PROMPT,
            knob=KnobType.SYSTEM_PROMPT_SUFFIX,
            knob_value="\n\nIf you encounter an unexpected error, report it clearly and suggest possible solutions.",
            description="Add generic error handling prompt",
            estimated_impact=0.10,
            risk_level=RiskLevel.LOW,
            confidence=0.4,
            rollback_value="",
            applicable_failure_types=[FailureType.UNKNOWN],
        ),
    ],
}


# ============================================================================
# CAUSAL DECOMPOSER - Main class for failure analysis
# ============================================================================


class CausalDecomposer:
    """
    Decomposes failure patterns into root causes and selects intervention strategies.

    This is the core intelligence component that:
    1. Analyzes failure contexts to understand root causes
    2. Maps failure types to appropriate intervention strategies
    3. Ranks strategies by expected impact and confidence

    Key Principle: The system turns KNOBS, not raw code.
    """

    def __init__(
        self,
        strategy_map: dict[FailureType, list[ImprovementStrategy]] | None = None,
        min_confidence: float = 0.5,
        max_strategies_per_failure: int = 3,
    ):
        self.strategy_map = strategy_map or STRATEGY_MAP
        self.min_confidence = min_confidence
        self.max_strategies_per_failure = max_strategies_per_failure

    async def decompose_failures(
        self,
        weak_area: WeakArea,
        failure_contexts: list[FailureContext] | None = None,
        db_session=None,
    ) -> list[FailureContext]:
        """
        Retrieve and analyze rich failure contexts for a weak area.

        Args:
            weak_area: The weak area to analyze
            failure_contexts: Pre-loaded failure contexts (optional, will load from DB if not provided)
            db_session: Optional async database session for loading from DB

        Returns:
            List of FailureContext objects with rich telemetry
        """
        if failure_contexts is not None:
            return failure_contexts

        if not db_session:
            logger.debug("No db_session provided for decompose_failures")
            return []

        # Load failure contexts from the database
        try:
            from sqlalchemy import select

            from app.models.mission_models import MissionImprovement

            result = await db_session.execute(
                select(MissionImprovement)
                .where(MissionImprovement.status == "pending")
                .order_by(MissionImprovement.created_at.desc())
                .limit(50)
            )
            improvements = result.scalars().all()

            contexts = []
            for imp in improvements:
                if imp.failure_type and imp.failure_context:
                    try:
                        failure_type = FailureType(imp.failure_type)
                    except ValueError:
                        failure_type = FailureType.UNKNOWN

                    ctx = FailureContext(
                        failure_type=failure_type,
                        severity=FailureSeverity.MEDIUM,
                        context_data={
                            "improvement_id": imp.id,
                            "detail": imp.failure_context,
                        },
                    )
                    contexts.append(ctx)

            if contexts:
                logger.info("Loaded %d failure contexts from database", len(contexts))
                return contexts

        except Exception as e:
            logger.warning("Failed to load failure contexts from DB: %s", e)

        logger.debug("No failure contexts found in database")
        return []

    def select_strategies(
        self,
        failures: list[FailureContext],
        weak_area: WeakArea | None = None,
    ) -> list[ImprovementStrategy]:
        """
        Select appropriate strategies based on failure distribution.

        Args:
            failures: List of failure contexts to analyze
            weak_area: Optional weak area for additional context

        Returns:
            Ranked list of improvement strategies to apply
        """
        if not failures:
            logger.info("No failures to analyze")
            return []

        # Count failures by type
        failure_counts: dict[FailureType, int] = {}
        for failure in failures:
            ft = failure.failure_type
            failure_counts[ft] = failure_counts.get(ft, 0) + 1

        # Get candidate strategies for each failure type
        candidate_strategies: list[tuple[ImprovementStrategy, int, float]] = []

        for failure_type, count in failure_counts.items():
            strategies = self.strategy_map.get(failure_type, [])

            for strategy in strategies:
                if strategy.confidence >= self.min_confidence:
                    # Score = count * estimated_impact * confidence
                    score = count * strategy.estimated_impact * strategy.confidence
                    candidate_strategies.append((strategy, count, score))

        # Sort by score (descending)
        candidate_strategies.sort(key=lambda x: x[2], reverse=True)

        # Deduplicate by knob (only one strategy per knob)
        seen_knobs = set()
        selected_strategies = []

        for strategy, count, score in candidate_strategies:
            if strategy.knob not in seen_knobs:
                seen_knobs.add(strategy.knob)
                selected_strategies.append(strategy)

                if len(selected_strategies) >= self.max_strategies_per_failure:
                    break

        logger.info(
            "Selected %s strategies from %s failures across %s failure types",
            len(selected_strategies),
            len(failures),
            len(failure_counts),
        )

        return selected_strategies

    def get_strategy_for_failure_type(
        self,
        failure_type: FailureType,
        index: int = 0,
    ) -> ImprovementStrategy | None:
        """
        Get a specific strategy for a failure type by index.

        Args:
            failure_type: The failure type to get strategy for
            index: Index of the strategy (0 = best, 1 = second best, etc.)

        Returns:
            ImprovementStrategy or None if not found
        """
        strategies = self.strategy_map.get(failure_type, [])
        if index < len(strategies):
            return strategies[index]
        return None

    def get_all_strategies_for_failure_type(
        self,
        failure_type: FailureType,
    ) -> list[ImprovementStrategy]:
        """Get all strategies for a failure type"""
        return self.strategy_map.get(failure_type, [])

    def analyze_failure_pattern(
        self,
        failures: list[FailureContext],
    ) -> dict[str, Any]:
        """
        Analyze failure patterns to provide insights.

        Args:
            failures: List of failure contexts

        Returns:
            Analysis results with patterns and recommendations
        """
        if not failures:
            return {"pattern": "no_failures", "recommendations": []}

        # Count by type
        type_counts: dict[FailureType, int] = {}
        severity_counts: dict[FailureSeverity, int] = {}
        tool_counts: dict[str, int] = {}
        total_latency = 0.0

        for failure in failures:
            type_counts[failure.failure_type] = (
                type_counts.get(failure.failure_type, 0) + 1
            )
            severity_counts[failure.severity] = (
                severity_counts.get(failure.severity, 0) + 1
            )
            if failure.tool_name:
                tool_counts[failure.tool_name] = (
                    tool_counts.get(failure.tool_name, 0) + 1
                )
            total_latency += failure.latency_ms

        # Identify dominant failure type
        dominant_type = (
            max(type_counts.items(), key=lambda x: x[1])[0]
            if type_counts
            else FailureType.UNKNOWN
        )

        # Identify most affected tool
        most_affected_tool = (
            max(tool_counts.items(), key=lambda x: x[1])[0] if tool_counts else None
        )

        # Get recommended strategies
        strategies = self.select_strategies(failures)

        return {
            "total_failures": len(failures),
            "failure_type_distribution": {
                ft.value: count for ft, count in type_counts.items()
            },
            "severity_distribution": {
                s.value: count for s, count in severity_counts.items()
            },
            "dominant_failure_type": dominant_type.value,
            "most_affected_tool": most_affected_tool,
            "average_latency_ms": total_latency / len(failures) if failures else 0,
            "recommended_strategies": [s.to_dict() for s in strategies],
            "pattern": self._classify_pattern(type_counts, severity_counts),
        }

    def _classify_pattern(
        self,
        type_counts: dict[FailureType, int],
        severity_counts: dict[FailureSeverity, int],
    ) -> str:
        """Classify the overall failure pattern"""
        total = sum(type_counts.values())
        if total == 0:
            return "no_failures"

        # Check for infrastructure-heavy pattern
        infra_types = {
            FailureType.TOOL_API_ERROR,
            FailureType.TOOL_TIMEOUT,
            FailureType.RESOURCE_EXHAUSTION,
            FailureType.CONNECTION_FAILURE,
            FailureType.RATE_LIMITED,
        }
        infra_count = sum(type_counts.get(ft, 0) for ft in infra_types)

        if infra_count / total > 0.7:
            return "infrastructure_heavy"

        # Check for LLM-heavy pattern
        llm_types = {
            FailureType.LLM_HALLUCINATION,
            FailureType.LLM_REFUSAL,
            FailureType.LLM_INSTRUCTION_DRIFT,
            FailureType.CONTEXT_OVERFLOW,
        }
        llm_count = sum(type_counts.get(ft, 0) for ft in llm_types)

        if llm_count / total > 0.7:
            return "llm_heavy"

        # Check for retrieval-heavy pattern
        retrieval_types = {
            FailureType.RETRIEVAL_MISS,
        }
        retrieval_count = sum(type_counts.get(ft, 0) for ft in retrieval_types)

        if retrieval_count / total > 0.5:
            return "retrieval_heavy"

        # Check for critical severity
        critical_count = severity_counts.get(FailureSeverity.CRITICAL, 0)
        if critical_count / total > 0.3:
            return "critical_failures"

        return "mixed"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_causal_decomposer() -> CausalDecomposer:
    """Factory function to get a CausalDecomposer instance"""
    return CausalDecomposer()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Constants
    "STRATEGY_MAP",
    # Classes
    "CausalDecomposer",
    # Dataclasses
    "ImprovementStrategy",
    # Enums
    "KnobType",
    "RiskLevel",
    "StrategyType",
    "WeakArea",
    # Functions
    "get_causal_decomposer",
]


# ============================================================================
# ALIAS METHODS FOR COMPATIBILITY
# ============================================================================

# These methods provide compatibility with improvement_loop_v2.py


async def analyze_failure_patterns(
    self,
    failures: list[FailureContext],
) -> list[WeakArea]:
    """
    Alias for analyze_failure_pattern() for compatibility.

    This method is called by improvement_loop_v2.py.

    Args:
        failures: List of failure contexts to analyze

    Returns:
        List of identified weak areas
    """
    return self.analyze_failure_pattern(failures)


async def generate_strategies(
    self,
    weak_area: WeakArea,
) -> list[ImprovementStrategy]:
    """
    Generate improvement strategies for a weak area.

    This method wraps select_strategies() for compatibility.

    Args:
        weak_area: The weak area to generate strategies for

    Returns:
        List of potential improvement strategies
    """
    return self.select_strategies(weak_area)
