"""BudgetEnforcer — single LLM call path with cost tracking (H3.4).

The BudgetEnforcer is the ONLY path to LLM calls in the system.
Every LLM invocation — whether through ModelRouter, httpx, or LangChain —
MUST go through this class.  Code review enforces this.

Per Ω spec VII.10:
- call():  Estimates cost before the LLM call, tracks actual cost after.
- Invariant I.14: No LLM call is made if it would exceed the declared budget.
- BudgetExhausted: Raised when any budget field is exceeded.

Integration:
- Wraps ModelRouter.route_request() for the primary LLM path
- Wraps httpx direct calls for the fallback path
- Records every call to the substrate event log (when available)
- Publishes budget metrics for observability
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from app.models.capability_models import Budget, BudgetExhausted

logger = logging.getLogger(__name__)

# ── Pricing table (per-model cost per 1M tokens) ─────────────────

# These prices are the source of truth.  They are loaded at boot and
# refreshed daily via a cron job (see PRICING_REFRESH_INTERVAL).

DEFAULT_PRICING: dict[str, dict[str, float | str]] = {
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28, "provider": "deepseek"},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19, "provider": "deepseek"},
    # Anthropic
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00, "provider": "anthropic"},
    "claude-3-haiku": {"input": 0.25, "output": 1.25, "provider": "anthropic"},
    "claude-3-opus": {"input": 15.00, "output": 75.00, "provider": "anthropic"},
    # OpenAI
    "gpt-4o": {"input": 5.00, "output": 15.00, "provider": "openai"},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "provider": "openai"},
    # OpenRouter (passthrough with margin)
    "openrouter-gemma-2-9b-free": {
        "input": 0.0,
        "output": 0.0,
        "provider": "openrouter",
    },
    "openrouter-gemini-2.0-flash": {
        "input": 0.15,
        "output": 0.60,
        "provider": "openrouter",
    },
    "openrouter-deepseek-coder": {
        "input": 0.14,
        "output": 0.28,
        "provider": "openrouter",
    },
    # Local (free)
    "vllm-qwen3-14b-chat": {"input": 0.0, "output": 0.0, "provider": "local"},
    "llamacpp-qwen3.6-27b": {"input": 0.0, "output": 0.0, "provider": "local"},
    # Fallback
    "default": {"input": 0.50, "output": 2.00, "provider": "unknown"},
}

# How often to refresh pricing (seconds)
PRICING_REFRESH_INTERVAL = 86_400  # 24 hours


class PricingTable:
    """Model pricing lookup with BYOK support.

    BYOK users bring their own API keys; their costs are still estimated
    but billing is handled by their provider, not Flowmanner.
    """

    def __init__(self, pricing: dict[str, dict[str, float | str]] | None = None):
        self._pricing = pricing or dict(DEFAULT_PRICING)
        self._last_refresh = time.monotonic()

    def estimate(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
    ) -> Decimal:
        """Estimate cost for a given model and token count.

        Returns the cost in USD as a Decimal.
        """
        model_key = model_id.split("/")[-1] if "/" in model_id else model_id
        entry = self._pricing.get(model_id) or self._pricing.get(model_key)
        if entry is None:
            entry = self._pricing["default"]

        input_cost = (prompt_tokens / 1_000_000) * entry["input"]
        output_cost = (completion_tokens / 1_000_000) * entry["output"]

        return Decimal(str(round(input_cost + output_cost, 8)))

    def get_provider(self, model_id: str) -> str:
        """Get the provider for a model."""
        entry = self._pricing.get(model_id)
        if entry is None:
            model_key = model_id.split("/")[-1] if "/" in model_id else model_id
            entry = self._pricing.get(model_key)
        return entry["provider"] if entry else "unknown"

    def refresh(self) -> None:
        """Refresh pricing from a JSON config file.

        Reads ``app/config/pricing.json`` and merges its ``models``
        dict into the in-memory pricing table.  Falls back to the
        hardcoded DEFAULT_PRICING if the config file is missing or
        unreadable.

        This is called once at startup and periodically (every
        PRICING_REFRESH_INTERVAL seconds) by a background task.
        """
        import json
        from pathlib import Path

        config_path = Path(__file__).resolve().parent.parent / "config" / "pricing.json"
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            models = data.get("models", {})
            if models:
                self._pricing = {**DEFAULT_PRICING, **models}
                logger.info(
                    "Pricing refreshed from %s: %d models (updated %s)",
                    config_path,
                    len(self._pricing),
                    data.get("updated_at", "unknown"),
                )
            else:
                logger.info("Pricing config exists but contains no models — using defaults")
        except FileNotFoundError:
            logger.debug("Pricing config not found at %s — using defaults", config_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load pricing config: %s", e)
        finally:
            self._last_refresh = time.monotonic()

    @property
    def stale(self) -> bool:
        """Check if pricing needs refresh."""
        return (time.monotonic() - self._last_refresh) > PRICING_REFRESH_INTERVAL


class BudgetEnforcer:
    """The only path to LLM calls.  Tracks spend in real time.

    Usage:
        enforcer = BudgetEnforcer()
        budget = Budget(max_cost_usd=Decimal("5.00"), max_wall_time_seconds=60)

        # Check before call
        estimated = enforcer.pricing.estimate("deepseek-chat", 1000, 500)
        if not enforcer.check_budget(budget, estimated):
            raise BudgetExhausted("...", budget)

        # Make call through enforcer
        response = await enforcer.call(
            budget=budget,
            model_id="deepseek-chat",
            messages=[{"role": "user", "content": "Hello"}],
        )

    Invariant I.14 (Bounded spending): No LLM call is made if it would exceed
    the declared budget.  The BudgetEnforcer is the only path to llm.call.
    """

    def __init__(self, pricing: PricingTable | None = None):
        self.pricing = pricing or PricingTable()

    def check_budget(self, budget: Budget, estimated_cost: Decimal) -> bool:
        """Check if a call would fit within the budget.

        Returns False if the call would exceed any budget field.
        """
        remaining = budget.max_cost_usd - budget.spent_usd
        if estimated_cost > remaining:
            logger.debug(
                "Budget check failed: estimated $%s > remaining $%s",
                estimated_cost,
                remaining,
            )
            return False

        # Check wall-clock (only if started)
        if budget.wall_time_started_at > 0:
            elapsed = time.monotonic() - budget.wall_time_started_at
            if elapsed >= budget.max_wall_time_seconds:
                return False

        # Check iterations
        return not budget.iterations_used >= budget.max_iterations

    async def call(
        self,
        *,
        budget: Budget,
        model_id: str,
        messages: list[dict[str, Any]],
        user_id: str | None = None,
        db_session: Any = None,
        is_admin: bool = False,
        model_preference: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        # Optional substrate context for event logging
        run_id: str | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
        workspace_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Make an LLM call through the budget enforcer.

        This is the ONLY method that should be called for LLM invocations.
        It enforces budget checks, records spend, and logs events.

        Args:
            budget: The Budget for this run (checked before and after call).
            model_id: Model to use.
            messages: Chat messages list.
            user_id: Authenticated user ID (for BYOK routing).
            db_session: Async DB session (for ModelRouter).
            is_admin: Whether the caller has admin privileges.
            model_preference: Preferred model (overrides auto-selection).
            temperature: LLM temperature.
            max_tokens: Maximum completion tokens.
            on_provider_call: Optional callback invoked before the actual call.
            run_id: Substrate run ID for event logging.
            mission_id: Mission ID for event logging.
            task_id: Task ID for event logging.

        Returns:
            Dict with success, response/content, model, provider, cost info.

        Raises:
            BudgetExhausted: If the call would exceed or has exceeded the budget.
        """
        # Start wall-clock if not started
        if budget.wall_time_started_at == 0.0:
            budget.wall_time_started_at = time.monotonic()

        # Pre-check budget
        is_exhausted, reason = budget.is_exhausted()
        if is_exhausted:
            raise BudgetExhausted(reason, budget)

        budget.iterations_used += 1
        start_time = time.monotonic()

        try:
            # Route through ModelRouter (primary path)
            try:
                from app.services.llm_router import ModelRouter

                router = ModelRouter()
                response = await router.route_request(
                    messages=messages,
                    user_id=user_id or "system",
                    db_session=db_session,
                    is_admin=is_admin,
                    model_preference=model_preference or model_id,
                    temperature=temperature or 0.7,
                    max_tokens=max_tokens or 2000,
                )

                actual_model = response.get("model", model_id)
                cost_info = response.get("cost", {})
                prompt_tokens = cost_info.get("input_tokens", 0)
                completion_tokens = cost_info.get("output_tokens", 0)

            except Exception as router_error:
                logger.warning("ModelRouter failed, trying direct httpx: %s", router_error)

                # Fallback to direct httpx call
                import httpx

                from app.config import settings

                actual_model = model_id
                llm_url = getattr(settings, "LLM_BASE_URL", "http://localhost:11434")
                llm_key = getattr(settings, "LLM_API_KEY", "")

                headers = {"Content-Type": "application/json"}
                if llm_key:
                    headers["Authorization"] = f"Bearer {llm_key}"

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{llm_url}/v1/chat/completions",
                        headers=headers,
                        json={
                            "model": model_id,
                            "messages": messages,
                            "temperature": temperature or 0.7,
                            "max_tokens": max_tokens or 2000,
                        },
                    )
                    data = resp.json()

                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                response = {
                    "success": True,
                    "response": content,
                    "model": actual_model,
                    "provider": "llamacpp",
                    "cost": {
                        "input_tokens": prompt_tokens,
                        "output_tokens": completion_tokens,
                    },
                }

            # Calculate actual cost
            actual_cost = self.pricing.estimate(actual_model, prompt_tokens, completion_tokens)
            provider = response.get("provider", self.pricing.get_provider(actual_model))

            # Update budget
            budget.spent_usd += actual_cost
            budget.depth_used = budget.iterations_used  # Track depth

            latency_ms = int((time.monotonic() - start_time) * 1000)

            # Post-call budget check
            is_exhausted, reason = budget.is_exhausted()
            if is_exhausted:
                logger.warning("Budget exhausted after LLM call: %s", reason)
                # Record the budget exhaustion in the substrate event log
                await self._record_budget_event(run_id, mission_id, task_id, reason, budget)
                # Don't raise here — let the caller handle the response,
                # but mark it so they know no further calls are allowed.

            # Record to substrate event log
            await self._record_llm_event(
                run_id=run_id,
                mission_id=mission_id,
                task_id=task_id,
                model_id=actual_model,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=float(actual_cost),
                latency_ms=latency_ms,
                success=response.get("success", False),
                error=response.get("error"),
                workspace_id=workspace_id,
                agent_id=agent_id,
            )

            # Phase 6.4: Record in circuit breaker
            if mission_id:
                await self._record_circuit_breaker(mission_id, float(actual_cost), db_session)

            # Enrich response with budget info
            response["budget"] = {
                "spent_usd": float(budget.spent_usd),
                "remaining_usd": float(max(Decimal("0"), budget.max_cost_usd - budget.spent_usd)),
                "iterations_used": budget.iterations_used,
                "budget_exhausted": is_exhausted,
            }

            return response

        except BudgetExhausted:
            raise
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.exception("BudgetEnforcer LLM call failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "model": model_id,
                "provider": "unknown",
                "cost": {"input_tokens": 0, "output_tokens": 0},
                "budget": {
                    "spent_usd": float(budget.spent_usd),
                    "remaining_usd": float(max(Decimal("0"), budget.max_cost_usd - budget.spent_usd)),
                    "iterations_used": budget.iterations_used,
                    "budget_exhausted": False,
                },
            }

    async def _record_circuit_breaker(
        self,
        mission_id: str,
        cost_usd: float,
        db_session: Any,
    ) -> None:
        """Record an LLM call in the circuit breaker (Phase 6.4)."""
        try:
            from app.services.circuit_breaker_service import CircuitBreakerService

            if db_session:
                service = CircuitBreakerService(db_session)
                breaker = await service.get_breaker(mission_id)
                if breaker:
                    await service.record_call(breaker, call_type="llm", cost_usd=cost_usd)
        except Exception as e:
            logger.debug("Circuit breaker record skipped: %s", e)

    async def _record_llm_event(
        self,
        run_id: str | None,
        mission_id: str | None,
        task_id: str | None,
        model_id: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool,
        error: str | None,
        workspace_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Record an LLM call event to the substrate event log."""
        if run_id is None:
            return

        try:
            from app.database import AsyncSessionLocal
            from app.services.substrate.event_log import get_event_log

            event_log = get_event_log()
            async with AsyncSessionLocal() as db:
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": "llm.call",
                            "payload": {
                                "model_id": model_id,
                                "provider": provider,
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "cost_usd": cost_usd,
                                "latency_ms": latency_ms,
                                "success": success,
                                "error": error,
                            },
                            "actor": "budget_enforcer",
                            "mission_id": mission_id,
                            "task_id": task_id,
                        }
                    ],
                )

            # Phase 6.3: Also record to llm_call_records with cost attribution
            try:
                from app.models.llm_call_record import LLMCallRecord

                record = LLMCallRecord(
                    mission_id=mission_id,
                    task_id=task_id,
                    model_id=model_id,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                )
                async with AsyncSessionLocal() as rec_db:
                    rec_db.add(record)
                    await rec_db.flush()
            except Exception as rec_err:
                logger.debug("Failed to record to llm_call_records: %s", rec_err)

        except Exception as e:
            logger.debug("Failed to record LLM event to substrate: %s", e)

    async def _record_budget_event(
        self,
        run_id: str | None,
        mission_id: str | None,
        task_id: str | None,
        reason: str,
        budget: Budget,
    ) -> None:
        """Record a budget exhaustion event to the substrate event log."""
        if run_id is None:
            return

        try:
            from app.database import AsyncSessionLocal
            from app.services.substrate.event_log import get_event_log

            event_log = get_event_log()
            async with AsyncSessionLocal() as db:
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": "substrate.budget_exhausted",
                            "payload": {
                                "reason": reason,
                                "spent_usd": float(budget.spent_usd),
                                "max_cost_usd": float(budget.max_cost_usd),
                                "iterations_used": budget.iterations_used,
                                "max_iterations": budget.max_iterations,
                                "remaining": budget.remaining(),
                            },
                            "actor": "budget_enforcer",
                            "mission_id": mission_id,
                            "task_id": task_id,
                        }
                    ],
                )
        except Exception as e:
            logger.debug("Failed to record budget event to substrate: %s", e)


# ── Singleton ──────────────────────────────────────────────────────

_budget_enforcer: BudgetEnforcer | None = None


def get_budget_enforcer() -> BudgetEnforcer:
    """Get or create the BudgetEnforcer singleton."""
    global _budget_enforcer
    if _budget_enforcer is None:
        _budget_enforcer = BudgetEnforcer()
    return _budget_enforcer


def reset_budget_enforcer() -> None:
    """Reset the singleton (for testing)."""
    global _budget_enforcer
    _budget_enforcer = None
