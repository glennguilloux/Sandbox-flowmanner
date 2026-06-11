"""Mission-scoped circuit breaker enforcement (H5.4).

Distinct from the external-dependency circuit breakers in
``app.core.circuit_breaker`` — this module enforces per-mission
exhaustion limits and destructive-action policy gates.

Enforced limits:
- max_llm_calls per mission
- max_cost_usd per mission
- max_duration_seconds per mission
- max_tool_calls per agent
- Destructive-action gate (requires HITL approval)

Integration: create a ``MissionCircuitBreaker`` instance at
the start of ``MissionExecutor.execute_mission``, call
``record_llm_call()`` after each LLM call, and call
``check()`` before each risky action.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


# ── Limit configuration ────────────────────────────────────────────


@dataclass
class MissionLimits:
    max_llm_calls: int = 150
    max_cost_usd: float = 5.00
    max_duration_seconds: int = 3600
    max_tool_calls_per_agent: int = 50
    destructive_actions_allowed: bool = False

    @classmethod
    def from_constraints(cls, constraints: dict | None) -> MissionLimits:
        """Build limits from mission constraints dict (e.g. from DB JSONB)."""
        if not constraints:
            return cls()
        return cls(
            max_llm_calls=constraints.get("max_llm_calls", 150),
            max_cost_usd=constraints.get("max_cost_usd", 5.00),
            max_duration_seconds=constraints.get("max_duration_seconds", 3600),
            max_tool_calls_per_agent=constraints.get("max_tool_calls_per_agent", 50),
            destructive_actions_allowed=constraints.get(
                "destructive_actions_allowed",
                False,
            ),
        )


# ── Exception ──────────────────────────────────────────────────────


class CircuitBreakerTrip(Exception):
    """Raised when a mission circuit breaker limit is exceeded."""

    def __init__(self, reason: str, limit: str, current: float, max_val: float):
        self.reason = reason
        self.limit = limit
        self.current = current
        self.max_val = max_val
        super().__init__(f"Circuit breaker [{limit}]: {reason} (current={current}, max={max_val})")


# ── Breaker ────────────────────────────────────────────────────────


@dataclass
class MissionCircuitBreaker:
    limits: MissionLimits
    started_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )
    llm_calls: int = 0
    cost_usd: float = 0.0
    tool_calls_by_agent: dict[str, int] = field(default_factory=dict)

    def record_llm_call(self, cost: float = 0.0) -> None:
        """Record an LLM call against the mission budget."""
        self.llm_calls += 1
        self.cost_usd += cost

    def record_tool_call(self, agent_id: str) -> None:
        """Record a tool call against the per-agent allowance."""
        current = self.tool_calls_by_agent.get(agent_id, 0)
        self.tool_calls_by_agent[agent_id] = current + 1

    def check(self, *, action_type: str = "", agent_id: str = "") -> None:
        """Validate all limits. Raises ``CircuitBreakerTrip`` on violation.

        Call this before any expensive or risky operation in the mission
        executor loop.
        """
        self._check_llm_calls()
        self._check_cost()
        self._check_duration()
        if action_type:
            self._check_destructive(action_type, agent_id)
        if agent_id:
            self._check_agent_tool_calls(agent_id)

    def _check_llm_calls(self) -> None:
        if self.llm_calls >= self.limits.max_llm_calls:
            raise CircuitBreakerTrip(
                reason="Max LLM calls exceeded",
                limit="max_llm_calls",
                current=self.llm_calls,
                max_val=self.limits.max_llm_calls,
            )

    def _check_cost(self) -> None:
        if self.cost_usd >= self.limits.max_cost_usd:
            raise CircuitBreakerTrip(
                reason="Max cost USD exceeded",
                limit="max_cost_usd",
                current=round(self.cost_usd, 4),
                max_val=self.limits.max_cost_usd,
            )

    def _check_duration(self) -> None:
        elapsed = (datetime.now(UTC) - self.started_at).total_seconds()
        if elapsed >= self.limits.max_duration_seconds:
            raise CircuitBreakerTrip(
                reason="Max duration exceeded",
                limit="max_duration_seconds",
                current=round(elapsed, 1),
                max_val=self.limits.max_duration_seconds,
            )

    def _check_agent_tool_calls(self, agent_id: str) -> None:
        current = self.tool_calls_by_agent.get(agent_id, 0)
        if current >= self.limits.max_tool_calls_per_agent:
            raise CircuitBreakerTrip(
                reason=f"Agent {agent_id} exhausted tool call allowance",
                limit="max_tool_calls_per_agent",
                current=current,
                max_val=self.limits.max_tool_calls_per_agent,
            )

    def _check_destructive(self, action_type: str, agent_id: str) -> None:
        is_destructive = action_type.startswith("destructive_") or action_type in (
            "delete_file",
            "drop_table",
            "transfer_funds",
            "send_email",
        )
        if is_destructive and not self.limits.destructive_actions_allowed:
            raise CircuitBreakerTrip(
                reason="Destructive action blocked — requires approval",
                limit="destructive_actions_allowed",
                current=1,
                max_val=0,
            )

    # ── Status ─────────────────────────────────────────────────────

    def status(self) -> dict:
        elapsed = (datetime.now(UTC) - self.started_at).total_seconds()
        return {
            "llm_calls": self.llm_calls,
            "cost_usd": round(self.cost_usd, 4),
            "elapsed_seconds": round(elapsed, 1),
            "limits": {
                "max_llm_calls": self.limits.max_llm_calls,
                "max_cost_usd": self.limits.max_cost_usd,
                "max_duration_seconds": self.limits.max_duration_seconds,
                "max_tool_calls_per_agent": self.limits.max_tool_calls_per_agent,
            },
            "tool_calls_by_agent": dict(self.tool_calls_by_agent),
        }
