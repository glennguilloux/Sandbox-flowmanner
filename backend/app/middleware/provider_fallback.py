"""
Provider Fallback Middleware
Week 1 Quick Win #2: Retry/rate-limit/fallback logic for LLM calls

Provides:
- Exponential backoff retry on rate limits
- Model fallback on failures
- Cost tracking integration
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class ProviderFallbackMiddleware:
    """
    Middleware that wraps LLM calls with retry and fallback logic.

    Features:
    - Exponential backoff on rate limits (429 errors)
    - Configurable retry attempts
    - Model fallback chain
    - Cost tracking via agent_economics table
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        fallback_models: list[str] | None = None,
        default_model: str = "qwen3.5:35b",
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.fallback_models = fallback_models or [
            "qwen3.5:35b",
            "gpt-4o-mini",
            "claude-3-haiku-20240307",
        ]
        self.default_model = default_model

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay = self.base_delay * (2**attempt)
        return min(delay, self.max_delay)

    async def execute_with_retry(
        self,
        func,
        *args,
        model: str = None,
        agent_id: str = None,
        task_id: str = None,
        **kwargs,
    ) -> Any:
        """
        Execute an LLM call with retry and fallback logic.

        Args:
            func: The async function to call (e.g., litellm.acompletion)
            model: The model to use
            agent_id: Agent ID for cost tracking
            task_id: Task ID for cost tracking
            **kwargs: Additional arguments for the function

        Returns:
            The response from the LLM call

        Raises:
            Exception: If all retries and fallbacks fail
        """
        models_to_try = [model or self.default_model]

        # Add fallback models if different from primary
        for fallback in self.fallback_models:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None

        for current_model in models_to_try:
            for attempt in range(self.max_retries):
                try:
                    # Update model in kwargs
                    kwargs["model"] = current_model

                    start_time = time.time()
                    response = await func(*args, **kwargs)
                    elapsed = time.time() - start_time

                    # Log successful call
                    logger.info(
                        "LLM call successful: model=%s, attempt=%s, elapsed=%.2fs",
                        current_model,
                        attempt + 1,
                        elapsed,
                    )

                    # Track cost if agent_id provided
                    if agent_id:
                        await self._track_cost(
                            response=response,
                            model=current_model,
                            agent_id=agent_id,
                            task_id=task_id,
                            elapsed=elapsed,
                        )

                    return response

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # Check if it's a rate limit error
                    is_rate_limit = (
                        "429" in error_str
                        or "rate limit" in error_str
                        or "too many requests" in error_str
                        or "quota" in error_str
                    )

                    if is_rate_limit and attempt < self.max_retries - 1:
                        delay = self._calculate_delay(attempt)
                        logger.warning(
                            "Rate limit hit for %s, retrying in %ss (attempt %s/%s)",
                            current_model,
                            delay,
                            attempt + 1,
                            self.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                    # Non-rate-limit error or max retries reached
                    logger.error("LLM call failed for %s: %s", current_model, e)
                    break

        # All models failed
        raise last_error or Exception("All LLM calls failed")

    async def _track_cost(
        self,
        response: Any,
        model: str,
        agent_id: str,
        task_id: str | None,
        elapsed: float,
    ):
        """Track cost in agent_economics table."""
        try:
            from app.database import SessionLocal
            from app.models.agent_economics import AgentEconomics

            # Extract usage from response
            usage = getattr(response, "usage", None)
            if not usage:
                return

            prompt_tokens = getattr(usage, "prompt_tokens", 0)
            completion_tokens = getattr(usage, "completion_tokens", 0)

            # Calculate cost (simplified - should use model pricing)
            cost = self._calculate_cost(model, prompt_tokens, completion_tokens)

            db = SessionLocal()
            try:
                record = AgentEconomics(
                    agent_id=agent_id,
                    task_id=task_id,
                    tokens_input=prompt_tokens,
                    tokens_output=completion_tokens,
                    cost_usd=cost,
                    model_name=model,
                    model_provider=self._get_provider(model),
                )
                db.add(record)
                db.commit()
            finally:
                db.close()

        except Exception as e:
            logger.warning("Failed to track cost: %s", e)

    def _calculate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Calculate cost based on model pricing (simplified)."""
        # Default pricing per 1M tokens
        pricing = {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "claude-3-opus": {"input": 15.00, "output": 75.00},
            "claude-3-sonnet": {"input": 3.00, "output": 15.00},
            "claude-3-haiku": {"input": 0.25, "output": 1.25},
            "qwen3.5:35b": {"input": 0.0, "output": 0.0},  # Local model
        }

        # Find matching pricing
        model_key = model.lower()
        for key, prices in pricing.items():
            if key in model_key:
                input_cost = (prompt_tokens / 1_000_000) * prices["input"]
                output_cost = (completion_tokens / 1_000_000) * prices["output"]
                return input_cost + output_cost

        # Default: assume local/free
        return 0.0

    def _get_provider(self, model: str) -> str:
        """Get provider name from model."""
        model_lower = model.lower()
        if "gpt" in model_lower or "o1" in model_lower:
            return "openai"
        elif "claude" in model_lower:
            return "anthropic"
        elif "gemini" in model_lower:
            return "google"
        elif "qwen" in model_lower or "llama" in model_lower:
            return "llamacpp"
        return "unknown"


# Singleton instance
_middleware = None


def get_provider_middleware() -> ProviderFallbackMiddleware:
    """Get or create the provider middleware singleton."""
    global _middleware
    if _middleware is None:
        _middleware = ProviderFallbackMiddleware()
    return _middleware


# Decorator for easy use
def with_retry_and_fallback(func):
    """Decorator to add retry and fallback to LLM calls."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        middleware = get_provider_middleware()
        return await middleware.execute_with_retry(func, *args, **kwargs)

    return wrapper
