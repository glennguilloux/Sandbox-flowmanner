"""Circuit Breaker service — Phase 6.4.

Provides:
- get_or_create(): Get or lazily create a breaker for a mission
- check_before_call(): Pre-call limit check (LLM or tool)
- record_call(): Increment counters after a call
- trigger(): Transition to TRIGGERED state
- reset(): Manual reset to ARMED state

Usage:
    service = CircuitBreakerService(db)
    breaker = await service.get_or_create(mission_id="...", workspace_id="...")
    allowed, reason = await service.check_before_call(breaker, call_type="llm")
    if not allowed:
        # Mission should pause
        ...
    await service.record_call(breaker, call_type="llm", cost_usd=0.005)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from app.models.circuit_breaker_models import (
    CircuitBreakerState,
    MissionCircuitBreaker,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CircuitBreakerService:
    """Per-mission circuit breaker management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(
        self,
        *,
        mission_id: str,
        workspace_id: str | None = None,
        max_llm_calls: int = 100,
        max_cost_usd: float = 10.0,
        max_duration_seconds: int = 3600,
        max_tool_calls: int = 200,
        destructive_actions_require_approval: bool = True,
    ) -> MissionCircuitBreaker:
        """Get existing breaker for a mission, or create one with defaults."""
        stmt = select(MissionCircuitBreaker).where(
            MissionCircuitBreaker.mission_id == mission_id
        )
        result = await self.db.execute(stmt)
        breaker = result.scalar_one_or_none()
        if breaker is not None:
            return breaker

        breaker = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=mission_id,
            workspace_id=workspace_id,
            max_llm_calls=max_llm_calls,
            max_cost_usd=max_cost_usd,
            max_duration_seconds=max_duration_seconds,
            max_tool_calls=max_tool_calls,
            destructive_actions_require_approval=destructive_actions_require_approval,
            state=CircuitBreakerState.ARMED.value,
        )
        self.db.add(breaker)
        await self.db.flush()
        logger.info(
            "Circuit breaker created for mission %s (max_llm=%d, max_cost=$%.2f)",
            mission_id, max_llm_calls, max_cost_usd,
        )
        return breaker

    async def check_before_call(
        self,
        breaker: MissionCircuitBreaker,
        call_type: str = "llm",
    ) -> tuple[bool, str]:
        """Check if a call is allowed before execution.

        Args:
            breaker: The circuit breaker for this mission.
            call_type: "llm" or "tool"

        Returns:
            (allowed, reason) — False if the breaker should block the call.
        """
        # Start the breaker on first check
        if breaker.started_at is None:
            breaker.started_at = datetime.now(UTC)

        if breaker.state == CircuitBreakerState.CIRCUIT_BROKEN.value:
            return False, "Circuit breaker is permanently broken — manual reset required"

        is_broken, reason = breaker.check_limits()
        if is_broken:
            # Transition to TRIGGERED
            breaker.state = CircuitBreakerState.TRIGGERED.value
            breaker.trigger_reason = reason
            breaker.triggered_at = datetime.now(UTC)
            breaker.trigger_count += 1
            await self.db.flush()

            logger.warning(
                "Circuit breaker triggered for mission %s: %s (count=%d)",
                breaker.mission_id, reason, breaker.trigger_count,
            )
            return False, reason

        return True, ""

    async def record_call(
        self,
        breaker: MissionCircuitBreaker,
        *,
        call_type: str = "llm",
        cost_usd: float = 0.0,
    ) -> None:
        """Record a call and update counters."""
        if call_type == "llm":
            breaker.llm_calls_made = (breaker.llm_calls_made or 0) + 1
        elif call_type == "tool":
            breaker.tool_calls_made = (breaker.tool_calls_made or 0) + 1
        breaker.cost_accumulated_usd = (breaker.cost_accumulated_usd or 0.0) + cost_usd
        await self.db.flush()

    async def trigger(
        self,
        breaker: MissionCircuitBreaker,
        reason: str,
    ) -> None:
        """Manually trigger the breaker (e.g., from abort)."""
        breaker.state = CircuitBreakerState.TRIGGERED.value
        breaker.trigger_reason = reason
        breaker.triggered_at = datetime.now(UTC)
        breaker.trigger_count += 1
        await self.db.flush()

    async def escalate_to_broken(self, breaker: MissionCircuitBreaker) -> None:
        """Escalate from TRIGGERED to CIRCUIT_BROKEN (permanent stop)."""
        breaker.state = CircuitBreakerState.CIRCUIT_BROKEN.value
        breaker.trigger_reason = f"Escalated after {breaker.trigger_count} triggers"
        await self.db.flush()
        logger.warning(
            "Circuit breaker BROKEN for mission %s after %d triggers",
            breaker.mission_id, breaker.trigger_count,
        )

    async def reset(self, breaker: MissionCircuitBreaker) -> None:
        """Manual reset to ARMED state."""
        breaker.state = CircuitBreakerState.ARMED.value
        breaker.trigger_reason = None
        breaker.triggered_at = None
        breaker.llm_calls_made = 0
        breaker.tool_calls_made = 0
        breaker.cost_accumulated_usd = 0.0
        breaker.started_at = datetime.now(UTC)
        await self.db.flush()
        logger.info("Circuit breaker reset for mission %s", breaker.mission_id)

    async def should_approve_action(
        self,
        breaker: MissionCircuitBreaker,
        action_name: str,
    ) -> bool:
        """Check if a specific action requires human approval."""
        return breaker.should_approve(action_name)

    async def get_breaker(self, mission_id: str) -> MissionCircuitBreaker | None:
        """Get the breaker for a mission."""
        stmt = select(MissionCircuitBreaker).where(
            MissionCircuitBreaker.mission_id == mission_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
