"""
Strategy Evolution Engine for Autonomous Self-Improvement System.

This module evolves strategies based on their effectiveness in production,
moving beyond the static STRATEGY_MAP to learned, adaptive strategies.

Phase 6C of the Autonomous Self-Improvement Architecture.
"""

import hashlib
import json
import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Any

logger = logging.getLogger(__name__)

# Import from previous phases
from .causal_decomposer import (
    StrategyType,
)
from .failure_types import FailureType
from .knob_manager import KnobManager

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class StrategyStatus(str, Enum):
    """Status of a strategy in the evolution lifecycle."""

    EXPERIMENTAL = "experimental"  # New, untested
    CANDIDATE = "candidate"  # Showing promise
    ESTABLISHED = "established"  # Proven effective
    DEPRECATED = "deprecated"  # No longer recommended
    RETIRED = "retired"  # Removed from active use


class EvolutionAction(str, Enum):
    """Actions that can be taken on a strategy."""

    PROMOTE = "promote"  # Move to higher status
    DEMOTE = "demote"  # Move to lower status
    MUTATE = "mutate"  # Create variation
    DEPRECATE = "deprecate"  # Mark as deprecated
    RETIRE = "retire"  # Remove from use
    NO_ACTION = "no_action"  # No change needed


@dataclass
class StrategyVariant:
    """A variant of a base strategy with modified parameters."""

    variant_id: str
    base_strategy_type: StrategyType
    parameters: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Performance tracking
    applications: int = 0
    successes: int = 0
    failures: int = 0
    success_rate: float = 0.0

    # Status
    status: StrategyStatus = StrategyStatus.EXPERIMENTAL
    confidence: float = 0.0

    # Parent tracking
    parent_variant_id: str | None = None
    generation: int = 0

    def calculate_success_rate(self) -> float:
        """Calculate and update success rate."""
        if self.applications == 0:
            self.success_rate = 0.0
        else:
            self.success_rate = self.successes / self.applications
        return self.success_rate

    def calculate_confidence(self) -> float:
        """Calculate confidence based on sample size and success rate."""
        self.calculate_success_rate()

        # Wilson score interval lower bound for confidence
        if self.applications == 0:
            self.confidence = 0.0
            return self.confidence

        n = self.applications
        p = self.success_rate
        z = 1.96  # 95% confidence

        denominator = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denominator
        margin = z * ((p * (1 - p) + z**2 / (4 * n)) / n) ** 0.5 / denominator

        self.confidence = max(0.0, center - margin)
        return self.confidence

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "variant_id": self.variant_id,
            "base_strategy_type": self.base_strategy_type.value,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat(),
            "applications": self.applications,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": self.success_rate,
            "status": self.status.value,
            "confidence": self.confidence,
            "parent_variant_id": self.parent_variant_id,
            "generation": self.generation,
        }


@dataclass
class EvolutionResult:
    """Result of an evolution action."""

    action: EvolutionAction
    variant: StrategyVariant
    reason: str
    old_status: StrategyStatus | None = None
    new_status: StrategyStatus | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action": self.action.value,
            "variant_id": self.variant.variant_id,
            "reason": self.reason,
            "old_status": self.old_status.value if self.old_status else None,
            "new_status": self.new_status.value if self.new_status else None,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================================
# STRATEGY EVOLVER
# ============================================================================


class StrategyEvolver:
    """
    Evolves strategies based on their effectiveness in production.

    This class manages the lifecycle of strategy variants, promoting
    successful ones and deprecating ineffective ones.
    """

    # Thresholds for evolution decisions
    PROMOTE_SUCCESS_THRESHOLD = 0.75
    PROMOTE_MIN_APPLICATIONS = 10
    DEPRECATE_SUCCESS_THRESHOLD = 0.25
    DEPRECATE_MIN_APPLICATIONS = 5
    RETIRE_SUCCESS_THRESHOLD = 0.15
    RETIRE_MIN_APPLICATIONS = 10

    # Mutation parameters
    MAX_GENERATIONS = 5
    MUTATION_RATE = 0.3
    PARAMETER_MUTATION_RANGE = 0.2

    def __init__(
        self,
        knob_manager: KnobManager | None = None,
        knowledge_graph=None,
    ):
        """
        Initialize the strategy evolver.

        Args:
            knob_manager: Optional knob manager for parameter mutations
            knowledge_graph: Optional knowledge graph for strategy storage
        """
        self.knob_manager = knob_manager
        self.knowledge_graph = knowledge_graph

        # Variant storage
        self._variants: dict[str, StrategyVariant] = {}
        self._strategy_variants: dict[StrategyType, set[str]] = defaultdict(set)

        # Evolution history
        self._evolution_history: list[EvolutionResult] = []

        # Initialize base variants from static strategies
        self._initialize_base_variants()

    def _initialize_base_variants(self) -> None:
        """Initialize base variants from the static STRATEGY_MAP."""
        # Create base variants for each strategy type
        base_parameters = {
            StrategyType.ADD_RETRY: {"max_retries": 3, "backoff": "exponential"},
            StrategyType.ADD_FALLBACK: {"fallback_strategy": "default"},  # type: ignore[attr-defined]
            StrategyType.ADJUST_TIMEOUT: {"timeout_multiplier": 2.0},  # type: ignore[attr-defined]
            StrategyType.REDUCE_COMPLEXITY: {"simplification_level": 1},  # type: ignore[attr-defined]
            StrategyType.ADD_CACHING: {"cache_ttl": 3600, "max_size": 1000},  # type: ignore[attr-defined]
            StrategyType.ADJUST_RATE_LIMIT: {"rate_limit_factor": 0.5},  # type: ignore[attr-defined]
            StrategyType.SWITCH_MODEL: {"model_tier": "standard"},  # type: ignore[attr-defined]
            StrategyType.ADD_VALIDATION: {"validation_level": "standard"},  # type: ignore[attr-defined]
            StrategyType.INCREASE_RESOURCES: {"resource_multiplier": 1.5},  # type: ignore[attr-defined]
            StrategyType.SIMPLIFY_PROMPT: {"max_tokens": 2000},  # type: ignore[attr-defined]
            StrategyType.ADD_CONTEXT: {"context_window": 4000},  # type: ignore[attr-defined]
            StrategyType.CHUNK_INPUT: {"chunk_size": 1000},  # type: ignore[attr-defined]
            StrategyType.ADD_MEMORY: {"memory_type": "short_term"},  # type: ignore[attr-defined]
            StrategyType.ENABLE_PARALLEL: {"max_parallel": 4},  # type: ignore[attr-defined]
            StrategyType.ADD_CIRCUIT_BREAKER: {
                "failure_threshold": 5,
                "reset_timeout": 60,
            },
            StrategyType.ADJUST_KNOB: {"knob_name": "default", "knob_value": None},  # type: ignore[attr-defined]
        }

        for strategy_type, params in base_parameters.items():
            variant = StrategyVariant(
                variant_id=f"base_{strategy_type.value}",
                base_strategy_type=strategy_type,
                parameters=params.copy(),  # type: ignore[attr-defined]
                status=StrategyStatus.ESTABLISHED,
                generation=0,
            )
            variant.confidence = 0.5  # Base confidence

            self._variants[variant.variant_id] = variant
            self._strategy_variants[strategy_type].add(variant.variant_id)

    async def evolve_strategy(
        self,
        base_strategy_type: StrategyType,
        performance_data: dict[str, float] | None = None,
    ) -> StrategyVariant | None:
        """
        Create a variation of a strategy based on performance data.

        Args:
            base_strategy_type: The strategy type to evolve
            performance_data: Optional performance metrics

        Returns:
            A new strategy variant, or None if evolution not beneficial
        """
        # Get best performing variant for this strategy
        best_variant = await self.get_best_variant(base_strategy_type)

        if not best_variant:
            return None

        # Check if we should evolve
        if best_variant.generation >= self.MAX_GENERATIONS:
            logger.debug('Max generations reached for %s', base_strategy_type.value)
            return None

        if best_variant.applications < self.PROMOTE_MIN_APPLICATIONS:
            logger.debug('Not enough applications to evolve %s', base_strategy_type.value)
            return None

        # Decide mutation type based on performance
        if best_variant.success_rate > 0.7:
            # Strategy is working well - try small optimization
            mutation_type = "optimize"
        elif best_variant.success_rate > 0.4:
            # Strategy is okay - try moderate changes
            mutation_type = "explore"
        else:
            # Strategy is struggling - try significant changes
            mutation_type = "diversify"

        # Create mutated parameters
        new_parameters = await self._mutate_parameters(
            best_variant.parameters,
            mutation_type,
            performance_data,
        )

        # Create new variant
        variant_id = self._generate_variant_id(base_strategy_type, new_parameters)

        new_variant = StrategyVariant(
            variant_id=variant_id,
            base_strategy_type=base_strategy_type,
            parameters=new_parameters,
            parent_variant_id=best_variant.variant_id,
            generation=best_variant.generation + 1,
            status=StrategyStatus.EXPERIMENTAL,
        )

        # Store variant
        self._variants[variant_id] = new_variant
        self._strategy_variants[base_strategy_type].add(variant_id)

        logger.info('Created new variant %s from %s (generation %s, mutation: %s)', variant_id, best_variant.variant_id, new_variant.generation, mutation_type)

        return new_variant

    async def deprecate_strategy(
        self,
        variant_id: str,
        reason: str = "Low success rate",
    ) -> EvolutionResult | None:
        """
        Mark a strategy variant as deprecated.

        Args:
            variant_id: The variant ID to deprecate
            reason: Reason for deprecation

        Returns:
            EvolutionResult if successful, None otherwise
        """
        variant = self._variants.get(variant_id)
        if not variant:
            return None

        old_status = variant.status
        variant.status = StrategyStatus.DEPRECATED

        result = EvolutionResult(
            action=EvolutionAction.DEPRECATE,
            variant=variant,
            reason=reason,
            old_status=old_status,
            new_status=StrategyStatus.DEPRECATED,
        )

        self._evolution_history.append(result)

        logger.info('Deprecated variant %s: %s', variant_id, reason)

        return result

    async def promote_strategy(
        self,
        variant_id: str,
    ) -> EvolutionResult | None:
        """
        Promote a strategy variant to a higher status.

        Args:
            variant_id: The variant ID to promote

        Returns:
            EvolutionResult if successful, None otherwise
        """
        variant = self._variants.get(variant_id)
        if not variant:
            return None

        old_status = variant.status

        # Determine new status
        if old_status == StrategyStatus.EXPERIMENTAL:
            new_status = StrategyStatus.CANDIDATE
        elif old_status == StrategyStatus.CANDIDATE:
            new_status = StrategyStatus.ESTABLISHED
        else:
            return None  # Cannot promote further

        variant.status = new_status

        result = EvolutionResult(
            action=EvolutionAction.PROMOTE,
            variant=variant,
            reason=f"Success rate {variant.success_rate:.2%} exceeds threshold",
            old_status=old_status,
            new_status=new_status,
        )

        self._evolution_history.append(result)

        logger.info('Promoted variant %s from %s to %s', variant_id, old_status.value, new_status.value)

        return result

    async def retire_strategy(
        self,
        variant_id: str,
        reason: str = "Consistently ineffective",
    ) -> EvolutionResult | None:
        """
        Retire a strategy variant from active use.

        Args:
            variant_id: The variant ID to retire
            reason: Reason for retirement

        Returns:
            EvolutionResult if successful, None otherwise
        """
        variant = self._variants.get(variant_id)
        if not variant:
            return None

        old_status = variant.status
        variant.status = StrategyStatus.RETIRED

        result = EvolutionResult(
            action=EvolutionAction.RETIRE,
            variant=variant,
            reason=reason,
            old_status=old_status,
            new_status=StrategyStatus.RETIRED,
        )

        self._evolution_history.append(result)

        logger.info('Retired variant %s: %s', variant_id, reason)

        return result

    async def record_outcome(
        self,
        variant_id: str,
        success: bool,
        context: dict[str, Any] | None = None,
    ) -> EvolutionResult | None:
        """
        Record the outcome of applying a strategy variant.

        Args:
            variant_id: The variant ID
            success: Whether the application succeeded
            context: Optional context information

        Returns:
            EvolutionResult if an action was taken, None otherwise
        """
        variant = self._variants.get(variant_id)
        if not variant:
            return None

        # Update statistics
        variant.applications += 1
        if success:
            variant.successes += 1
        else:
            variant.failures += 1

        variant.calculate_confidence()

        # Check for automatic actions
        action_result = await self._check_automatic_action(variant)

        return action_result

    async def _check_automatic_action(
        self,
        variant: StrategyVariant,
    ) -> EvolutionResult | None:
        """Check if automatic action should be taken on a variant."""
        # Check for promotion
        if variant.status == StrategyStatus.EXPERIMENTAL:
            if (
                variant.success_rate >= self.PROMOTE_SUCCESS_THRESHOLD
                and variant.applications >= self.PROMOTE_MIN_APPLICATIONS
            ):
                return await self.promote_strategy(variant.variant_id)

        elif variant.status == StrategyStatus.CANDIDATE:
            if (
                variant.success_rate >= self.PROMOTE_SUCCESS_THRESHOLD
                and variant.applications >= self.PROMOTE_MIN_APPLICATIONS * 2
            ):
                return await self.promote_strategy(variant.variant_id)

        # Check for deprecation
        if variant.status in (StrategyStatus.EXPERIMENTAL, StrategyStatus.CANDIDATE):
            if (
                variant.success_rate <= self.DEPRECATE_SUCCESS_THRESHOLD
                and variant.applications >= self.DEPRECATE_MIN_APPLICATIONS
            ):
                return await self.deprecate_strategy(
                    variant.variant_id,
                    f"Success rate {variant.success_rate:.2%} below threshold",
                )

        # Check for retirement
        if variant.status == StrategyStatus.DEPRECATED:
            if (
                variant.success_rate <= self.RETIRE_SUCCESS_THRESHOLD
                and variant.applications >= self.RETIRE_MIN_APPLICATIONS
            ):
                return await self.retire_strategy(
                    variant.variant_id,
                    f"Success rate {variant.success_rate:.2%} consistently low",
                )

        return None

    async def get_best_variant(
        self,
        strategy_type: StrategyType,
        min_status: StrategyStatus = StrategyStatus.EXPERIMENTAL,
    ) -> StrategyVariant | None:
        """
        Get the best performing variant for a strategy type.

        Args:
            strategy_type: The strategy type
            min_status: Minimum status to consider

        Returns:
            Best variant, or None if none available
        """
        variant_ids = self._strategy_variants[strategy_type]

        status_order = {
            StrategyStatus.ESTABLISHED: 3,
            StrategyStatus.CANDIDATE: 2,
            StrategyStatus.EXPERIMENTAL: 1,
            StrategyStatus.DEPRECATED: 0,
            StrategyStatus.RETIRED: -1,
        }

        min_status_level = status_order.get(min_status, 0)

        candidates = [
            self._variants[vid]
            for vid in variant_ids
            if vid in self._variants
            and status_order.get(self._variants[vid].status, 0) >= min_status_level
        ]

        if not candidates:
            return None

        # Sort by confidence * success_rate, preferring higher status
        candidates.sort(
            key=lambda v: (
                status_order.get(v.status, 0),
                v.confidence * v.success_rate if v.applications > 0 else 0.5,
            ),
            reverse=True,
        )

        return candidates[0]

    async def get_variants_for_failure(
        self,
        failure_type: FailureType,
    ) -> list[StrategyVariant]:
        """
        Get recommended strategy variants for a failure type.

        Args:
            failure_type: The failure type

        Returns:
            List of recommended variants
        """
        # Map failure types to strategy types (from causal_decomposer)
        failure_strategy_map = {
            FailureType.TOOL_TIMEOUT: [
                StrategyType.ADD_RETRY,
                StrategyType.ADJUST_TIMEOUT,  # type: ignore[attr-defined]
            ],
            FailureType.LLM_TIMEOUT: [  # type: ignore[attr-defined]
                StrategyType.ADJUST_TIMEOUT,  # type: ignore[attr-defined]
                StrategyType.SWITCH_MODEL,  # type: ignore[attr-defined]
            ],
            FailureType.RATE_LIMITED: [
                StrategyType.ADJUST_RATE_LIMIT,  # type: ignore[attr-defined]
                StrategyType.ADD_CIRCUIT_BREAKER,
            ],
            FailureType.LLM_HALLUCINATION: [
                StrategyType.SWITCH_MODEL,  # type: ignore[attr-defined]
                StrategyType.ADD_VALIDATION,  # type: ignore[attr-defined]
            ],
            FailureType.CONTEXT_OVERFLOW: [
                StrategyType.CHUNK_INPUT,  # type: ignore[attr-defined]
                StrategyType.SIMPLIFY_PROMPT,  # type: ignore[attr-defined]
            ],
            FailureType.MEMORY_EXHAUSTION: [  # type: ignore[attr-defined]
                StrategyType.REDUCE_COMPLEXITY,  # type: ignore[attr-defined]
                StrategyType.CHUNK_INPUT,  # type: ignore[attr-defined]
            ],
            FailureType.TOOL_FAILURE: [  # type: ignore[attr-defined]
                StrategyType.ADD_FALLBACK,  # type: ignore[attr-defined]
                StrategyType.ADD_RETRY,
            ],
            FailureType.LLM_ERROR: [  # type: ignore[attr-defined]
                StrategyType.ADD_FALLBACK,  # type: ignore[attr-defined]
                StrategyType.SWITCH_MODEL,  # type: ignore[attr-defined]
            ],
            FailureType.INVALID_INPUT: [  # type: ignore[attr-defined]
                StrategyType.ADD_VALIDATION,  # type: ignore[attr-defined]
                StrategyType.SIMPLIFY_PROMPT,  # type: ignore[attr-defined]
            ],
            FailureType.INVALID_OUTPUT: [  # type: ignore[attr-defined]
                StrategyType.ADD_VALIDATION,  # type: ignore[attr-defined]
                StrategyType.ADJUST_KNOB,  # type: ignore[attr-defined]
            ],
            FailureType.PERMISSION_DENIED: [  # type: ignore[attr-defined]
                StrategyType.ADD_FALLBACK,  # type: ignore[attr-defined]
                StrategyType.REDUCE_COMPLEXITY,  # type: ignore[attr-defined]
            ],
            FailureType.RESOURCE_EXHAUSTED: [  # type: ignore[attr-defined]
                StrategyType.INCREASE_RESOURCES,  # type: ignore[attr-defined]
                StrategyType.REDUCE_COMPLEXITY,  # type: ignore[attr-defined]
            ],
            FailureType.NETWORK_ERROR: [  # type: ignore[attr-defined]
                StrategyType.ADD_RETRY,
                StrategyType.ADD_CIRCUIT_BREAKER,
            ],
            FailureType.DEPENDENCY_FAILURE: [  # type: ignore[attr-defined]
                StrategyType.ADD_FALLBACK,  # type: ignore[attr-defined]
                StrategyType.ADD_CIRCUIT_BREAKER,
            ],
        }

        strategy_types = failure_strategy_map.get(failure_type, [])

        variants = []
        for strategy_type in strategy_types:
            variant = await self.get_best_variant(strategy_type)
            if variant:
                variants.append(variant)

        return variants

    async def run_evolution_cycle(self) -> list[EvolutionResult]:
        """
        Run a complete evolution cycle across all strategies.

        Returns:
            List of evolution actions taken
        """
        results = []

        for strategy_type in StrategyType:
            variant_ids = self._strategy_variants[strategy_type]

            for variant_id in list(variant_ids):
                variant = self._variants.get(variant_id)
                if not variant:
                    continue

                # Skip retired variants
                if variant.status == StrategyStatus.RETIRED:
                    continue

                # Check for automatic actions
                action_result = await self._check_automatic_action(variant)
                if action_result:
                    results.append(action_result)

                # Consider evolution for successful strategies
                if (
                    variant.status == StrategyStatus.ESTABLISHED
                    and variant.success_rate > 0.8
                    and variant.applications >= self.PROMOTE_MIN_APPLICATIONS * 2
                ):
                    new_variant = await self.evolve_strategy(
                        strategy_type,
                        {"success_rate": variant.success_rate},
                    )

                    if new_variant:
                        results.append(
                            EvolutionResult(
                                action=EvolutionAction.MUTATE,
                                variant=new_variant,
                                reason=f"Created variant from high-performing {variant_id}",
                                old_status=None,
                                new_status=StrategyStatus.EXPERIMENTAL,
                            )
                        )

        return results

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _generate_variant_id(
        self,
        strategy_type: StrategyType,
        parameters: dict[str, Any],
    ) -> str:
        """Generate a unique variant ID."""
        param_str = json.dumps(parameters, sort_keys=True)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        return f"{strategy_type.value}_{param_hash}"

    async def _mutate_parameters(
        self,
        base_params: dict[str, Any],
        mutation_type: str,
        performance_data: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Mutate parameters based on mutation type.

        Args:
            base_params: Base parameters to mutate
            mutation_type: Type of mutation (optimize, explore, diversify)
            performance_data: Optional performance hints

        Returns:
            Mutated parameters
        """
        new_params = base_params.copy()

        # Determine mutation intensity
        if mutation_type == "optimize":
            intensity = 0.1  # Small changes
        elif mutation_type == "explore":
            intensity = 0.25  # Moderate changes
        else:  # diversify
            intensity = 0.5  # Large changes

        for key, value in new_params.items():
            if random.random() > self.MUTATION_RATE:
                continue

            if isinstance(value, int):
                # Mutate integer
                delta = max(1, int(value * intensity))
                if random.random() > 0.5:
                    new_params[key] = value + delta
                else:
                    new_params[key] = max(1, value - delta)

            elif isinstance(value, float):
                # Mutate float
                delta = value * intensity  # type: ignore[assignment]
                if random.random() > 0.5:
                    new_params[key] = value + delta
                else:
                    new_params[key] = max(0.1, value - delta)

            elif isinstance(value, str) and key in (
                "backoff",
                "model_tier",
                "memory_type",
            ):
                # Mutate enum-like strings
                options = {
                    "backoff": ["exponential", "linear", "fixed"],
                    "model_tier": ["standard", "premium", "economy"],
                    "memory_type": ["short_term", "long_term", "episodic"],
                }
                if key in options:
                    other_options = [o for o in options[key] if o != value]
                    if other_options:
                        new_params[key] = random.choice(other_options)

        return new_params

    def get_variant(self, variant_id: str) -> StrategyVariant | None:
        """Get a variant by ID."""
        return self._variants.get(variant_id)

    def get_all_variants(
        self,
        strategy_type: StrategyType | None = None,
        status: StrategyStatus | None = None,
    ) -> list[StrategyVariant]:
        """Get all variants, optionally filtered."""
        variants = list(self._variants.values())

        if strategy_type:
            variants = [v for v in variants if v.base_strategy_type == strategy_type]

        if status:
            variants = [v for v in variants if v.status == status]

        return variants

    def get_evolution_history(
        self,
        limit: int = 100,
    ) -> list[EvolutionResult]:
        """Get recent evolution history."""
        return self._evolution_history[-limit:]

    def get_statistics(self) -> dict[str, Any]:
        """Get evolver statistics."""
        status_counts: dict[str, int] = defaultdict(int)
        for variant in self._variants.values():
            status_counts[variant.status.value] += 1

        return {
            "total_variants": len(self._variants),
            "variants_by_status": dict(status_counts),
            "evolution_events": len(self._evolution_history),
            "strategies_with_variants": len(self._strategy_variants),
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_strategy_evolver: StrategyEvolver | None = None


def get_strategy_evolver() -> StrategyEvolver:
    """Get the singleton strategy evolver instance."""
    global _strategy_evolver
    if _strategy_evolver is None:
        _strategy_evolver = StrategyEvolver()
    return _strategy_evolver


def initialize_strategy_evolver(
    knob_manager: KnobManager | None = None,
    knowledge_graph=None,
) -> StrategyEvolver:
    """Initialize the strategy evolver."""
    global _strategy_evolver
    _strategy_evolver = StrategyEvolver(knob_manager, knowledge_graph)
    return _strategy_evolver
