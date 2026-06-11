"""
Cost Optimization Engine - Token tracking and budget management

Provides comprehensive cost tracking, estimation, budget enforcement,
and optimization recommendations for the MetaLoop agent system.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PricingModel(Enum):
    """Token pricing models"""

    PER_TOKEN = "per_token"
    PER_1K_TOKENS = "per_1k_tokens"
    PER_MILLION = "per_million"


@dataclass
class ModelPricing:
    """Pricing configuration for a model"""

    model_id: str
    input_cost_per_1k: float  # Cost per 1k input tokens
    output_cost_per_1k: float  # Cost per 1k output tokens
    currency: str = "USD"
    effective_date: datetime = field(default_factory=datetime.utcnow)

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate total cost for token usage"""
        input_cost = (input_tokens / 1000) * self.input_cost_per_1k
        output_cost = (output_tokens / 1000) * self.output_cost_per_1k
        return input_cost + output_cost


@dataclass
class TokenUsage:
    """Token usage record"""

    agent_id: str
    query_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tool_name: str | None = None
    operation: str = "inference"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "query_id": self.query_id,
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "operation": self.operation,
            "metadata": self.metadata,
        }


@dataclass
class Budget:
    """Budget configuration for an agent or user"""

    entity_id: str  # agent_id or user_id
    entity_type: str  # "agent" or "user"
    daily_limit: float
    weekly_limit: float
    monthly_limit: float
    alert_threshold: float = 0.8  # Alert at 80% usage
    hard_limit: bool = True  # Block when exceeded
    created_at: datetime = field(default_factory=datetime.utcnow)

    def check_within_limits(self, current_spend: dict[str, float]) -> tuple[bool, str | None]:
        """Check if current spend is within budget limits"""
        if current_spend.get("daily", 0) > self.daily_limit:
            return (
                False,
                f"Daily budget exceeded: ${current_spend['daily']:.2f} > ${self.daily_limit:.2f}",
            )
        if current_spend.get("weekly", 0) > self.weekly_limit:
            return (
                False,
                f"Weekly budget exceeded: ${current_spend['weekly']:.2f} > ${self.weekly_limit:.2f}",
            )
        if current_spend.get("monthly", 0) > self.monthly_limit:
            return (
                False,
                f"Monthly budget exceeded: ${current_spend['monthly']:.2f} > ${self.monthly_limit:.2f}",
            )
        return True, None

    def should_alert(self, current_spend: dict[str, float]) -> tuple[bool, str]:
        """Check if spending has reached alert threshold"""
        alerts = []
        if current_spend.get("daily", 0) >= self.daily_limit * self.alert_threshold:
            alerts.append(f"Daily: {current_spend['daily']:.2f}/{self.daily_limit:.2f}")
        if current_spend.get("weekly", 0) >= self.weekly_limit * self.alert_threshold:
            alerts.append(f"Weekly: {current_spend['weekly']:.2f}/{self.weekly_limit:.2f}")
        if current_spend.get("monthly", 0) >= self.monthly_limit * self.alert_threshold:
            alerts.append(f"Monthly: {current_spend['monthly']:.2f}/{self.monthly_limit:.2f}")

        return len(alerts) > 0, ", ".join(alerts)


@dataclass
class CostEstimate:
    """Estimated cost for an operation"""

    operation: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float
    confidence: float  # 0.0 to 1.0
    model_id: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_cost": self.estimated_cost,
            "confidence": self.confidence,
            "model_id": self.model_id,
            "alternatives": self.alternatives,
        }


@dataclass
class OptimizationRecommendation:
    """Cost optimization recommendation"""

    recommendation_id: str
    category: str  # "model_selection", "caching", "batching", "prompt_optimization"
    description: str
    potential_savings: float  # Estimated monthly savings
    impact: str  # "low", "medium", "high"
    implementation_effort: str  # "easy", "moderate", "complex"
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class CostOptimizer:
    """
    Central cost optimization service.

    Features:
    - Token usage tracking per agent/query
    - Cost estimation before execution
    - Budget enforcement with alerts
    - Cost-aware tool selection
    - Optimization recommendations
    """

    # Default model pricing (GPT-4 style pricing as baseline)
    DEFAULT_PRICING = {
        "gpt-4": ModelPricing("gpt-4", 0.03, 0.06),
        "gpt-4-turbo": ModelPricing("gpt-4-turbo", 0.01, 0.03),
        "gpt-3.5-turbo": ModelPricing("gpt-3.5-turbo", 0.0005, 0.0015),
        "claude-3-opus": ModelPricing("claude-3-opus", 0.015, 0.075),
        "claude-3-sonnet": ModelPricing("claude-3-sonnet", 0.003, 0.015),
        "claude-3-haiku": ModelPricing("claude-3-haiku", 0.00025, 0.00125),
        "default": ModelPricing("default", 0.01, 0.03),
    }

    def __init__(self):
        self._usage_records: list[TokenUsage] = []
        self._budgets: dict[str, Budget] = {}  # entity_id -> Budget
        self._model_pricing: dict[str, ModelPricing] = dict(self.DEFAULT_PRICING)
        self._spend_cache: dict[str, dict[str, float]] = {}  # entity_id -> {daily, weekly, monthly}
        self._recommendations: list[OptimizationRecommendation] = []
        self._tool_cost_history: dict[str, list[float]] = {}  # tool_name -> [costs]
        self._lock = asyncio.Lock()
        self._alert_handlers: list[Callable[..., Any]] = []

    def register_alert_handler(self, handler: Callable[..., Any]):
        """Register a handler for budget alerts"""
        self._alert_handlers.append(handler)

    async def _send_alert(self, entity_id: str, message: str, level: str = "warning"):
        """Send alert to registered handlers"""
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(entity_id, message, level)
                else:
                    handler(entity_id, message, level)
            except Exception as e:
                logger.error("Alert handler failed: %s", e)

    def set_model_pricing(self, pricing: ModelPricing):
        """Set or update pricing for a model"""
        self._model_pricing[pricing.model_id] = pricing
        logger.info(
            "Updated pricing for model %s: $%s/1k input, $%s/1k output",
            pricing.model_id,
            pricing.input_cost_per_1k,
            pricing.output_cost_per_1k,
        )

    def get_model_pricing(self, model_id: str) -> ModelPricing:
        """Get pricing for a model, with fallback to default"""
        return self._model_pricing.get(model_id, self._model_pricing["default"])

    async def set_budget(self, budget: Budget):
        """Set budget for an agent or user"""
        async with self._lock:
            self._budgets[budget.entity_id] = budget
            self._spend_cache[budget.entity_id] = {
                "daily": 0.0,
                "weekly": 0.0,
                "monthly": 0.0,
            }
            logger.info(
                "Set budget for %s %s: $%s/day, $%s/week, $%s/month",
                budget.entity_type,
                budget.entity_id,
                budget.daily_limit,
                budget.weekly_limit,
                budget.monthly_limit,
            )

    async def get_budget(self, entity_id: str) -> Budget | None:
        """Get budget for an entity"""
        return self._budgets.get(entity_id)

    async def estimate_cost(
        self,
        operation: str,
        model_id: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> CostEstimate:
        """
        Estimate cost for an operation.

        Args:
            operation: Operation type (e.g., "inference", "embedding", "tool_execution")
            model_id: Model to use
            estimated_input_tokens: Estimated input token count
            estimated_output_tokens: Estimated output tokens (defaults to input * 0.5)
            context: Additional context for estimation

        Returns:
            CostEstimate with cost and alternatives
        """
        if estimated_output_tokens is None:
            # Default: output is ~50% of input
            estimated_output_tokens = int(estimated_input_tokens * 0.5)

        pricing = self.get_model_pricing(model_id)
        estimated_cost = pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)

        # Calculate confidence based on historical data
        confidence = 0.7  # Base confidence
        if operation in self._tool_cost_history:
            history = self._tool_cost_history[operation]
            if len(history) > 10:
                confidence = 0.9
            elif len(history) > 5:
                confidence = 0.8

        # Find cheaper alternatives
        alternatives = []
        for alt_model, alt_pricing in self._model_pricing.items():
            if alt_model != model_id and alt_model != "default":
                alt_cost = alt_pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)
                if alt_cost < estimated_cost:
                    alternatives.append(
                        {
                            "model_id": alt_model,
                            "estimated_cost": alt_cost,
                            "savings": estimated_cost - alt_cost,
                            "savings_percent": ((estimated_cost - alt_cost) / estimated_cost) * 100,
                        }
                    )

        # Sort alternatives by savings
        alternatives.sort(key=lambda x: float(x["savings"]), reverse=True)  # type: ignore[arg-type]
        return CostEstimate(
            operation=operation,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_cost=estimated_cost,
            confidence=confidence,
            model_id=model_id,
            alternatives=alternatives[:3],  # Top 3 alternatives
        )

    async def check_budget(self, entity_id: str, estimated_cost: float) -> tuple[bool, str | None]:
        """
        Check if an operation would exceed budget.

        Args:
            entity_id: Agent or user ID
            estimated_cost: Estimated cost of operation

        Returns:
            (allowed, reason) tuple
        """
        budget = self._budgets.get(entity_id)
        if not budget:
            return True, None  # No budget set, allow

        spend = self._spend_cache.get(entity_id, {"daily": 0.0, "weekly": 0.0, "monthly": 0.0})

        # Check if adding this cost would exceed limits
        projected = {
            "daily": spend["daily"] + estimated_cost,
            "weekly": spend["weekly"] + estimated_cost,
            "monthly": spend["monthly"] + estimated_cost,
        }

        allowed, reason = budget.check_within_limits(projected)

        if not allowed and budget.hard_limit:
            logger.warning("Budget blocked for %s: %s", entity_id, reason)
            return False, reason

        # Check for alert threshold
        should_alert, alert_msg = budget.should_alert(projected)
        if should_alert:
            await self._send_alert(entity_id, f"Budget alert: {alert_msg}", "warning")

        return True, None

    async def record_usage(
        self,
        agent_id: str,
        query_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        tool_name: str | None = None,
        operation: str = "inference",
        metadata: dict[str, Any] | None = None,
    ) -> TokenUsage:
        """
        Record token usage and update spend tracking.

        Args:
            agent_id: Agent that used tokens
            query_id: Query identifier
            model_id: Model used
            input_tokens: Input token count
            output_tokens: Output token count
            tool_name: Tool that generated usage
            operation: Operation type
            metadata: Additional metadata

        Returns:
            TokenUsage record
        """
        pricing = self.get_model_pricing(model_id)
        cost = pricing.calculate_cost(input_tokens, output_tokens)

        usage = TokenUsage(
            agent_id=agent_id,
            query_id=query_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost=cost,
            tool_name=tool_name,
            operation=operation,
            metadata=metadata or {},
        )

        async with self._lock:
            self._usage_records.append(usage)

            # Update spend cache
            if agent_id not in self._spend_cache:
                self._spend_cache[agent_id] = {
                    "daily": 0.0,
                    "weekly": 0.0,
                    "monthly": 0.0,
                }
            self._spend_cache[agent_id]["daily"] += cost
            self._spend_cache[agent_id]["weekly"] += cost
            self._spend_cache[agent_id]["monthly"] += cost

            # Track tool costs
            if tool_name:
                if tool_name not in self._tool_cost_history:
                    self._tool_cost_history[tool_name] = []
                self._tool_cost_history[tool_name].append(cost)

        logger.debug(
            "Recorded usage: %s used %s tokens ($%.4f)",
            agent_id,
            input_tokens + output_tokens,
            cost,
        )
        return usage

    async def get_usage_stats(
        self,
        entity_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get usage statistics.

        Args:
            entity_id: Filter by agent/user (optional)
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Usage statistics dictionary
        """
        records = self._usage_records

        # Apply filters
        if entity_id:
            records = [r for r in records if r.agent_id == entity_id]
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]

        if not records:
            return {
                "total_records": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "by_model": {},
                "by_tool": {},
            }

        total_tokens = sum(r.total_tokens for r in records)
        total_cost = sum(r.cost for r in records)

        # Aggregate by model
        by_model: dict[str, dict[str, float]] = {}
        for r in records:
            if r.model_id not in by_model:
                by_model[r.model_id] = {"tokens": 0, "cost": 0.0}
            by_model[r.model_id]["tokens"] += r.total_tokens
            by_model[r.model_id]["cost"] += r.cost

        # Aggregate by tool
        by_tool: dict[str, dict[str, float]] = {}
        for r in records:
            tool = r.tool_name or "direct"
            if tool not in by_tool:
                by_tool[tool] = {"tokens": 0, "cost": 0.0, "calls": 0}
            by_tool[tool]["tokens"] += r.total_tokens
            by_tool[tool]["cost"] += r.cost
            by_tool[tool]["calls"] += 1

        return {
            "total_records": len(records),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "avg_cost_per_query": total_cost / len(records),
            "by_model": by_model,
            "by_tool": by_tool,
            "time_range": {
                "start": min(r.timestamp for r in records).isoformat(),
                "end": max(r.timestamp for r in records).isoformat(),
            },
        }

    async def get_spend_summary(self, entity_id: str) -> dict[str, Any]:
        """Get current spend summary for an entity"""
        budget = self._budgets.get(entity_id)
        spend = self._spend_cache.get(entity_id, {"daily": 0.0, "weekly": 0.0, "monthly": 0.0})

        result = {"entity_id": entity_id, "spend": spend, "budget": None}

        if budget:
            result["budget"] = {
                "daily_limit": budget.daily_limit,
                "weekly_limit": budget.weekly_limit,
                "monthly_limit": budget.monthly_limit,
                "daily_remaining": max(0, budget.daily_limit - spend["daily"]),
                "weekly_remaining": max(0, budget.weekly_limit - spend["weekly"]),
                "monthly_remaining": max(0, budget.monthly_limit - spend["monthly"]),
                "daily_percent_used": ((spend["daily"] / budget.daily_limit * 100) if budget.daily_limit > 0 else 0),
                "weekly_percent_used": (
                    (spend["weekly"] / budget.weekly_limit * 100) if budget.weekly_limit > 0 else 0
                ),
                "monthly_percent_used": (
                    (spend["monthly"] / budget.monthly_limit * 100) if budget.monthly_limit > 0 else 0
                ),
            }

        return result

    async def select_cost_optimal_model(
        self,
        models: list[str],
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        quality_threshold: float = 0.8,
    ) -> tuple[str, float]:
        """
        Select the most cost-effective model.

        Args:
            models: List of candidate model IDs
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens
            quality_threshold: Minimum quality score (0-1)

        Returns:
            (selected_model, estimated_cost) tuple
        """
        # Model quality scores (simplified - in production, use benchmarks)
        quality_scores = {
            "gpt-4": 0.95,
            "gpt-4-turbo": 0.92,
            "claude-3-opus": 0.94,
            "claude-3-sonnet": 0.88,
            "gpt-3.5-turbo": 0.75,
            "claude-3-haiku": 0.72,
            "default": 0.70,
        }

        best_model = None
        best_cost = float("inf")

        for model_id in models:
            quality = quality_scores.get(model_id, 0.70)
            if quality < quality_threshold:
                continue

            pricing = self.get_model_pricing(model_id)
            cost = pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)

            if cost < best_cost:
                best_cost = cost
                best_model = model_id

        if best_model is None:
            # Fallback to first model if none meet threshold
            best_model = models[0] if models else "default"
            pricing = self.get_model_pricing(best_model)
            best_cost = pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)

        return best_model, best_cost

    async def generate_recommendations(self) -> list[OptimizationRecommendation]:
        """Generate cost optimization recommendations"""
        recommendations = []

        # Analyze tool usage patterns
        for tool_name, costs in self._tool_cost_history.items():
            if len(costs) < 5:
                continue

            avg_cost = sum(costs) / len(costs)

            # High-cost tool recommendation
            if avg_cost > 0.10:  # More than 10 cents average
                recommendations.append(
                    OptimizationRecommendation(
                        recommendation_id=f"high_cost_tool_{tool_name}",
                        category="model_selection",
                        description=f"Consider using a cheaper model for {tool_name} (avg cost: ${avg_cost:.4f})",
                        potential_savings=avg_cost * len(costs) * 0.5,  # Estimate 50% savings
                        impact="medium",
                        implementation_effort="easy",
                        metadata={"tool_name": tool_name, "avg_cost": avg_cost},
                    )
                )

        # Analyze model distribution
        stats = await self.get_usage_stats()
        for model_id, model_stats in stats.get("by_model", {}).items():
            if model_stats["cost"] > 10.0:  # More than $10 spent
                recommendations.append(
                    OptimizationRecommendation(
                        recommendation_id=f"model_usage_{model_id}",
                        category="model_selection",
                        description=f"Review {model_id} usage: ${model_stats['cost']:.2f} spent. Consider alternatives.",
                        potential_savings=model_stats["cost"] * 0.3,
                        impact="high",
                        implementation_effort="moderate",
                        metadata={
                            "model_id": model_id,
                            "total_cost": model_stats["cost"],
                        },
                    )
                )

        # Cache recommendations
        self._recommendations = recommendations
        return recommendations

    async def reset_daily_spend(self):
        """Reset daily spend counters (call from scheduler)"""
        async with self._lock:
            for entity_id in self._spend_cache:
                self._spend_cache[entity_id]["daily"] = 0.0
            logger.info("Reset daily spend counters")

    async def reset_weekly_spend(self):
        """Reset weekly spend counters (call from scheduler)"""
        async with self._lock:
            for entity_id in self._spend_cache:
                self._spend_cache[entity_id]["weekly"] = 0.0
            logger.info("Reset weekly spend counters")

    async def reset_monthly_spend(self):
        """Reset monthly spend counters (call from scheduler)"""
        async with self._lock:
            for entity_id in self._spend_cache:
                self._spend_cache[entity_id]["monthly"] = 0.0
            logger.info("Reset monthly spend counters")


# Singleton instance
_cost_optimizer: CostOptimizer | None = None


def get_cost_optimizer() -> CostOptimizer:
    """Get the singleton CostOptimizer instance"""
    global _cost_optimizer
    if _cost_optimizer is None:
        _cost_optimizer = CostOptimizer()
        logger.info("Initialized CostOptimizer singleton")
    return _cost_optimizer
