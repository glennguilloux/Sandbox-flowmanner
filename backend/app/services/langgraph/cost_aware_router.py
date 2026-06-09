#!/usr/bin/env python3
"""
Cost-Aware LLM Router with Intelligent Model Selection

Features:
- Token cost tracking per model (input/output)
- Task complexity classification (simple/medium/complex)
- Intelligent routing based on cost optimization
- Quality vs cost tradeoff configuration
- Fallback chains based on task complexity
- Manual model selection override API
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels for routing decisions"""

    SIMPLE = "simple"  # Basic queries, simple Q&A, formatting
    MEDIUM = "medium"  # Code review, analysis, moderate reasoning
    COMPLEX = "complex"  # Multi-step reasoning, complex code generation, research
    CRITICAL = "critical"  # Mission-critical tasks requiring best available model


@dataclass
class ModelCosts:
    """Token costs for a model (per 1M tokens)"""

    input_cost: float  # Cost per 1M input tokens
    output_cost: float  # Cost per 1M output tokens
    is_local: bool = False  # Local models have zero monetary cost
    quality_score: float = 0.8  # Quality score 0-1
    speed_score: float = 0.8  # Speed score 0-1
    max_context: int = 4096  # Maximum context window

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate total cost for given token counts"""
        if self.is_local:
            return 0.0
        return (input_tokens / 1_000_000) * self.input_cost + (
            output_tokens / 1_000_000
        ) * self.output_cost


@dataclass
class RoutingDecision:
    """Result of a routing decision"""

    selected_model: str
    complexity: TaskComplexity
    estimated_cost: float
    estimated_tokens: tuple[int, int]  # (input, output)
    fallback_chain: list[str]
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UsageRecord:
    """Record of actual model usage for cost tracking"""

    model_id: str
    input_tokens: int
    output_tokens: int
    actual_cost: float
    task_complexity: TaskComplexity
    timestamp: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    latency_ms: float = 0.0


class CostTracker:
    """Tracks token usage and costs across models"""

    def __init__(self, retention_hours: int = 168):  # 7 days default
        self.retention_hours = retention_hours
        self.usage_records: list[UsageRecord] = []
        self.model_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_requests": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "total_errors": 0,
                "avg_latency_ms": 0.0,
            }
        )

    def record_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        complexity: TaskComplexity,
        success: bool = True,
        latency_ms: float = 0.0,
    ):
        """Record a usage event"""
        record = UsageRecord(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_cost=cost,
            task_complexity=complexity,
            success=success,
            latency_ms=latency_ms,
        )
        self.usage_records.append(record)

        # Update stats
        stats = self.model_stats[model_id]
        stats["total_requests"] += 1
        stats["total_input_tokens"] += input_tokens
        stats["total_output_tokens"] += output_tokens
        stats["total_cost"] += cost
        if not success:
            stats["total_errors"] += 1

        # Update rolling average latency
        prev_avg = stats["avg_latency_ms"]
        n = stats["total_requests"]
        stats["avg_latency_ms"] = prev_avg + (latency_ms - prev_avg) / n

        # Cleanup old records
        self._cleanup_old_records()

    def _cleanup_old_records(self):
        """Remove records older than retention period"""
        cutoff = datetime.now(UTC) - timedelta(hours=self.retention_hours)
        self.usage_records = [r for r in self.usage_records if r.timestamp > cutoff]

    def get_model_stats(self, model_id: str) -> dict[str, Any]:
        """Get statistics for a specific model"""
        return dict(self.model_stats.get(model_id, {}))

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all models"""
        return {k: dict(v) for k, v in self.model_stats.items()}

    def get_total_cost(self, model_id: str | None = None) -> float:
        """Get total cost, optionally filtered by model"""
        if model_id:
            return self.model_stats[model_id]["total_cost"]
        return sum(s["total_cost"] for s in self.model_stats.values())

    def get_cost_by_complexity(self) -> dict[str, float]:
        """Get total cost broken down by task complexity"""
        costs = {c.value: 0.0 for c in TaskComplexity}
        for record in self.usage_records:
            costs[record.task_complexity.value] += record.actual_cost
        return costs


class TaskClassifier:
    """Classifies task complexity based on input analysis"""

    # Patterns that indicate complexity levels
    SIMPLE_PATTERNS = [
        r"^(hi|hello|hey|thanks|thank you|ok|yes|no)[\s!.]*$",
        r"^(what is|define|explain briefly)",
        r"^(list|show|get|find)\s+(all|the|my)",
        r"\b(simple|basic|quick|brief)\b",
        r"\b(format|convert|translate)\b.*\b(to|into)\b",
        r"^\w+\s*\?\s*$",  # Single word questions
    ]

    MEDIUM_PATTERNS = [
        r"\b(analyze|review|compare|summarize|explain)\b",
        r"\b(how (do|can|to)|why (does|is|did))\b",
        r"\b(debug|fix|solve|implement)\b.*\b(simple|small|basic)\b",
        r"\b(write|create|generate)\b.*\b(function|script|snippet)\b",
        r"\b(refactor|optimize|improve)\b",
        r"\b(test|testing)\b.*\b(unit|simple)\b",
    ]

    COMPLEX_PATTERNS = [
        r"\b(architecture|design|system|distributed)\b",
        r"\b(multi|multiple|several|complex)\b.*\b(step|phase|component)\b",
        r"\b(create|build|develop|implement)\b.*\b(application|service|api|system)\b",
        r"\b(integrate|integration|connect)\b.*\b(multiple|several|external)\b",
        r"\b(migrate|migration|transform|rewrite)\b",
        r"\b(machine learning|ml|ai|neural|model training)\b",
        r"\b(security|secure|encrypt|authenticate)\b.*\b(implement|design)\b",
        r"\b(performance|scale|scaling|optimize)\b.*\b(critical|high|important)\b",
    ]

    CRITICAL_PATTERNS = [
        r"\b(critical|urgent|important|production)\b",
        r"\b(security|vulnerability|exploit|breach)\b",
        r"\b(data loss|recovery|backup|restore)\b",
        r"\b(legal|compliance|audit|regulation)\b",
        r"\b(mission|critical|essential|vital)\b",
    ]

    # Token count thresholds for complexity estimation
    TOKEN_THRESHOLDS = {
        TaskComplexity.SIMPLE: (0, 500),
        TaskComplexity.MEDIUM: (500, 2000),
        TaskComplexity.COMPLEX: (2000, 8000),
        TaskComplexity.CRITICAL: (8000, float("inf")),
    }

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance"""
        self._simple_re = [re.compile(p, re.IGNORECASE) for p in self.SIMPLE_PATTERNS]
        self._medium_re = [re.compile(p, re.IGNORECASE) for p in self.MEDIUM_PATTERNS]
        self._complex_re = [re.compile(p, re.IGNORECASE) for p in self.COMPLEX_PATTERNS]
        self._critical_re = [
            re.compile(p, re.IGNORECASE) for p in self.CRITICAL_PATTERNS
        ]

    def classify(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        estimated_tokens: int | None = None,
    ) -> TaskComplexity:
        """
        Classify task complexity based on prompt analysis.

        Args:
            prompt: The user prompt to analyze
            context: Optional context information
            estimated_tokens: Optional pre-calculated token estimate

        Returns:
            TaskComplexity level
        """
        # Check for critical patterns first
        for pattern in self._critical_re:
            if pattern.search(prompt):
                return TaskComplexity.CRITICAL

        # Check for complex patterns
        for pattern in self._complex_re:
            if pattern.search(prompt):
                return TaskComplexity.COMPLEX

        # Check for medium patterns
        for pattern in self._medium_re:
            if pattern.search(prompt):
                return TaskComplexity.MEDIUM

        # Check for simple patterns
        for pattern in self._simple_re:
            if pattern.search(prompt):
                return TaskComplexity.SIMPLE

        # Use token count if available
        if estimated_tokens:
            for complexity, (low, high) in self.TOKEN_THRESHOLDS.items():
                if low <= estimated_tokens < high:
                    return complexity

        # Use prompt length as fallback
        word_count = len(prompt.split())
        if word_count < 20:
            return TaskComplexity.SIMPLE
        elif word_count < 100:
            return TaskComplexity.MEDIUM
        elif word_count < 500:
            return TaskComplexity.COMPLEX
        else:
            return TaskComplexity.CRITICAL

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text (rough approximation)"""
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4


class CostAwareRouter:
    """
    Intelligent LLM router that optimizes for cost while maintaining quality.

    Features:
    - Task complexity classification
    - Cost-aware model selection
    - Configurable quality/cost tradeoff
    - Fallback chains per complexity level
    - Usage tracking and reporting
    """

    # Default model costs (per 1M tokens)
    DEFAULT_MODEL_COSTS = {
        # Local models (free)
        "local-qwen3.5": ModelCosts(
            0, 0, is_local=True, quality_score=0.85, speed_score=0.7, max_context=262144
        ),
        "vllm-qwen3-14b-chat": ModelCosts(
            0, 0, is_local=True, quality_score=0.80, speed_score=0.8, max_context=32768
        ),
        "llamacpp-qwen3.6-27b": ModelCosts(
            0, 0, is_local=True, quality_score=0.90, speed_score=0.7, max_context=32768
        ),
        "llamacpp-qwen2.5-coder-7b": ModelCosts(
            0, 0, is_local=True, quality_score=0.75, speed_score=0.9, max_context=8192
        ),
        "llamacpp-qwen2.5-1.5b": ModelCosts(
            0, 0, is_local=True, quality_score=0.65, speed_score=0.95, max_context=4096
        ),
        # DeepSeek (low cost)
        "deepseek-reasoner": ModelCosts(
            0.55,
            2.19,
            is_local=False,
            quality_score=0.90,
            speed_score=0.6,
            max_context=128000,
        ),
        "deepseek-chat": ModelCosts(
            0.14,
            0.28,
            is_local=False,
            quality_score=0.85,
            speed_score=0.8,
            max_context=128000,
        ),
        # Free cloud models
        "openrouter-gemma-2-9b-free": ModelCosts(
            0, 0, is_local=True, quality_score=0.70, speed_score=0.8, max_context=8192
        ),
        # Paid models (when allowed)
        "claude-3-5-sonnet": ModelCosts(
            3.0,
            15.0,
            is_local=False,
            quality_score=0.95,
            speed_score=0.7,
            max_context=200000,
        ),
        "claude-3-haiku": ModelCosts(
            0.25,
            1.25,
            is_local=False,
            quality_score=0.85,
            speed_score=0.9,
            max_context=200000,
        ),
        "openrouter-gpt-4o": ModelCosts(
            2.5,
            10.0,
            is_local=False,
            quality_score=0.93,
            speed_score=0.7,
            max_context=128000,
        ),
        "openrouter-gemini-2.0-flash": ModelCosts(
            0.075,
            0.30,
            is_local=False,
            quality_score=0.88,
            speed_score=0.9,
            max_context=1000000,
        ),
    }

    # Default routing configuration per complexity level
    DEFAULT_ROUTING_CONFIG = {
        TaskComplexity.SIMPLE: {
            "preferred_models": [
                "llamacpp-qwen2.5-1.5b",
                "llamacpp-qwen2.5-coder-7b",
                "deepseek-chat",
            ],
            "fallback_chain": [
                "llamacpp-qwen2.5-1.5b",
                "llamacpp-qwen2.5-coder-7b",
                "vllm-qwen3-14b-chat",
                "deepseek-chat",
            ],
            "min_quality_score": 0.6,
            "prefer_speed": True,
        },
        TaskComplexity.MEDIUM: {
            "preferred_models": [
                "vllm-qwen3-14b-chat",
                "deepseek-chat",
                "llamacpp-qwen2.5-coder-7b",
            ],
            "fallback_chain": [
                "vllm-qwen3-14b-chat",
                "deepseek-chat",
                "local-qwen3.5",
                "deepseek-reasoner",
            ],
            "min_quality_score": 0.75,
            "prefer_speed": False,
        },
        TaskComplexity.COMPLEX: {
            "preferred_models": [
                "local-qwen3.5",
                "deepseek-reasoner",
                "vllm-qwen3-14b-chat",
            ],
            "fallback_chain": [
                "local-qwen3.5",
                "deepseek-reasoner",
                "vllm-qwen3-14b-chat",
                "deepseek-chat",
            ],
            "min_quality_score": 0.85,
            "prefer_speed": False,
        },
        TaskComplexity.CRITICAL: {
            "preferred_models": [
                "deepseek-reasoner",
                "local-qwen3.5",
            ],
            "fallback_chain": [
                "deepseek-reasoner",
                "local-qwen3.5",
                "deepseek-chat",
            ],
            "min_quality_score": 0.90,
            "prefer_speed": False,
        },
    }

    def __init__(
        self,
        llm_manager,
        model_costs: dict[str, ModelCosts] | None = None,
        routing_config: dict[TaskComplexity, dict[str, Any]] | None = None,
        cost_quality_tradeoff: float = 0.5,  # 0 = cheapest, 1 = highest quality
        allow_paid_models: bool = False,
    ):
        """
        Initialize the cost-aware router.

        Args:
            llm_manager: LLMManager instance for model access
            model_costs: Optional custom model costs
            routing_config: Optional custom routing configuration
            cost_quality_tradeoff: Balance between cost and quality (0-1)
            allow_paid_models: Whether to include paid models in routing
        """
        self.llm_manager = llm_manager
        self.model_costs = model_costs or self.DEFAULT_MODEL_COSTS.copy()
        self.routing_config = routing_config or self.DEFAULT_ROUTING_CONFIG.copy()
        self.cost_quality_tradeoff = max(0.0, min(1.0, cost_quality_tradeoff))
        self.allow_paid_models = allow_paid_models

        self.cost_tracker = CostTracker()
        self.task_classifier = TaskClassifier()

        # Manual override state
        self._manual_override: str | None = None
        self._override_expiry: datetime | None = None

        # Model health tracking
        self._model_health: dict[str, bool] = {}
        self._last_health_check: dict[str, datetime] = {}

    def set_cost_quality_tradeoff(self, value: float):
        """Set the cost-quality tradeoff value (0=cheapest, 1=highest quality)"""
        self.cost_quality_tradeoff = max(0.0, min(1.0, value))

    def set_manual_override(self, model_id: str, duration_minutes: int = 60):
        """Set a manual model override"""
        self._manual_override = model_id
        self._override_expiry = datetime.now(UTC) + timedelta(minutes=duration_minutes)
        logger.info(
            "Manual override set to %s for %s minutes", model_id, duration_minutes
        )

    def clear_manual_override(self):
        """Clear manual override"""
        self._manual_override = None
        self._override_expiry = None
        logger.info("Manual override cleared")

    def _is_override_active(self) -> bool:
        """Check if manual override is active"""
        if self._manual_override and self._override_expiry:
            if datetime.now(UTC) < self._override_expiry:
                return True
            else:
                # Override expired
                self.clear_manual_override()
        return False

    def estimate_request_cost(
        self, prompt: str, model_id: str, estimated_output_tokens: int = 500
    ) -> tuple[int, int, float]:
        """
        Estimate the cost of a request.

        Returns:
            Tuple of (input_tokens, output_tokens, estimated_cost)
        """
        input_tokens = self.task_classifier.estimate_tokens(prompt)
        output_tokens = estimated_output_tokens

        costs = self.model_costs.get(model_id)
        estimated_cost = (
            costs.calculate_cost(input_tokens, output_tokens) if costs else 0.0
        )

        return input_tokens, output_tokens, estimated_cost

    def select_model(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        force_complexity: TaskComplexity | None = None,
        force_model: str | None = None,
    ) -> RoutingDecision:
        """
        Select the optimal model for a given prompt.

        Args:
            prompt: The user prompt
            context: Optional context information
            force_complexity: Override complexity classification
            force_model: Force a specific model (highest priority)

        Returns:
            RoutingDecision with selected model and metadata
        """
        # Check for forced model first
        if force_model:
            complexity = force_complexity or self.task_classifier.classify(
                prompt, context
            )
            input_tokens, output_tokens, cost = self.estimate_request_cost(
                prompt, force_model
            )
            return RoutingDecision(
                selected_model=force_model,
                complexity=complexity,
                estimated_cost=cost,
                estimated_tokens=(input_tokens, output_tokens),
                fallback_chain=self.routing_config.get(complexity, {}).get(  # type: ignore[arg-type]
                    "fallback_chain", []
                ),
                reason="Forced model selection",
            )

        # Check for manual override
        if self._is_override_active():
            complexity = force_complexity or self.task_classifier.classify(
                prompt, context
            )
            input_tokens, output_tokens, cost = self.estimate_request_cost(
                prompt, self._manual_override
            )
            return RoutingDecision(
                selected_model=self._manual_override,
                complexity=complexity,
                estimated_cost=cost,
                estimated_tokens=(input_tokens, output_tokens),
                fallback_chain=self.routing_config.get(complexity, {}).get(  # type: ignore[arg-type]
                    "fallback_chain", []
                ),
                reason="Manual override active",
            )

        # Classify task complexity
        complexity = force_complexity or self.task_classifier.classify(prompt, context)

        # Get routing config for this complexity
        config = self.routing_config.get(
            complexity, self.routing_config[TaskComplexity.MEDIUM]
        )
        preferred_models = config.get("preferred_models", [])
        fallback_chain = config.get("fallback_chain", [])
        min_quality = config.get("min_quality_score", 0.7)

        # Filter models based on availability and constraints
        available_models = self._get_available_models(preferred_models, min_quality)

        if not available_models:
            # Fall back to fallback chain
            available_models = self._get_available_models(fallback_chain, min_quality)

        if not available_models:
            # Last resort: use any available model
            all_models = list(self.llm_manager.models.keys())
            available_models = self._get_available_models(all_models, 0.0)

        if not available_models:
            raise RuntimeError("No models available for routing")

        # Select best model based on cost-quality tradeoff
        selected_model = self._select_optimal_model(
            available_models, prompt, complexity
        )

        # Estimate cost
        input_tokens, output_tokens, cost = self.estimate_request_cost(
            prompt, selected_model
        )

        return RoutingDecision(
            selected_model=selected_model,
            complexity=complexity,
            estimated_cost=cost,
            estimated_tokens=(input_tokens, output_tokens),
            fallback_chain=fallback_chain,
            reason=f"Selected based on {complexity.value} complexity and cost-quality tradeoff={self.cost_quality_tradeoff:.2f}",
        )

    def _get_available_models(
        self, model_ids: list[str], min_quality: float
    ) -> list[str]:
        """Get list of available models meeting quality threshold"""
        available = []
        for model_id in model_ids:
            # Check if model exists in manager
            if model_id not in self.llm_manager.models:
                continue

            # Check quality threshold
            costs = self.model_costs.get(model_id)
            if costs and costs.quality_score < min_quality:
                continue

            # Check if paid model and allowed
            if costs and not costs.is_local and not self.allow_paid_models:
                # Check if it's a paid model (has non-zero cost)
                if costs.input_cost > 0 or costs.output_cost > 0:
                    # Special case: DeepSeek is allowed even with costs (very cheap)
                    if "deepseek" not in model_id.lower():
                        continue

            available.append(model_id)

        return available

    def _select_optimal_model(
        self, available_models: list[str], prompt: str, complexity: TaskComplexity
    ) -> str:
        """Select optimal model based on cost-quality tradeoff"""
        if len(available_models) == 1:
            return available_models[0]

        # Score each model
        scores = {}
        for model_id in available_models:
            costs = self.model_costs.get(model_id)
            if not costs:
                continue

            # Calculate normalized scores
            quality_score = costs.quality_score

            # Cost score (inverse - lower cost = higher score)
            if costs.is_local:
                cost_score = 1.0
            else:
                # Normalize cost (assuming max cost of $10 per 1M tokens)
                max_cost = 10.0
                avg_cost = (costs.input_cost + costs.output_cost) / 2
                cost_score = 1.0 - (avg_cost / max_cost)

            # Combine scores based on tradeoff
            combined_score = (
                self.cost_quality_tradeoff * quality_score
                + (1 - self.cost_quality_tradeoff) * cost_score
            )

            scores[model_id] = combined_score

        # Return model with highest score
        if scores:
            return max(scores.keys(), key=lambda m: scores[m])

        # Fallback to first available
        return available_models[0]

    def record_actual_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        complexity: TaskComplexity,
        success: bool = True,
        latency_ms: float = 0.0,
    ):
        """Record actual usage for cost tracking"""
        costs = self.model_costs.get(model_id)
        actual_cost = (
            costs.calculate_cost(input_tokens, output_tokens) if costs else 0.0
        )

        self.cost_tracker.record_usage(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=actual_cost,
            complexity=complexity,
            success=success,
            latency_ms=latency_ms,
        )

    def get_routing_stats(self) -> dict[str, Any]:
        """Get comprehensive routing statistics"""
        return {
            "total_cost": self.cost_tracker.get_total_cost(),
            "cost_by_model": {
                model_id: stats["total_cost"]
                for model_id, stats in self.cost_tracker.get_all_stats().items()
            },
            "cost_by_complexity": self.cost_tracker.get_cost_by_complexity(),
            "model_stats": self.cost_tracker.get_all_stats(),
            "current_tradeoff": self.cost_quality_tradeoff,
            "manual_override": (
                self._manual_override if self._is_override_active() else None
            ),
            "allow_paid_models": self.allow_paid_models,
        }

    def get_model_recommendations(self, prompt: str) -> dict[str, Any]:
        """Get model recommendations for a prompt without routing"""
        complexity = self.task_classifier.classify(prompt)
        config = self.routing_config.get(complexity, {})

        recommendations = []
        for model_id in config.get("preferred_models", []):
            costs = self.model_costs.get(model_id)
            if costs:
                input_tokens, output_tokens, cost = self.estimate_request_cost(
                    prompt, model_id
                )
                recommendations.append(
                    {
                        "model_id": model_id,
                        "quality_score": costs.quality_score,
                        "speed_score": costs.speed_score,
                        "is_local": costs.is_local,
                        "estimated_cost": cost,
                        "estimated_tokens": {
                            "input": input_tokens,
                            "output": output_tokens,
                        },
                    }
                )

        return {
            "complexity": complexity.value,
            "recommendations": recommendations,
            "fallback_chain": config.get("fallback_chain", []),
        }


# Singleton instance
_cost_aware_router: CostAwareRouter | None = None


def get_cost_aware_router(llm_manager=None, **kwargs) -> CostAwareRouter:
    """Get or create the cost-aware router singleton"""
    global _cost_aware_router
    if _cost_aware_router is None:
        if llm_manager is None:
            from app.core.llm_config import get_llm_manager

            llm_manager = get_llm_manager()
        _cost_aware_router = CostAwareRouter(llm_manager, **kwargs)
    return _cost_aware_router
