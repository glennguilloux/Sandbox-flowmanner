#!/usr/bin/env python3
"""
Webhook Retry Manager

Handles retry logic for failed webhook processing with exponential backoff.
"""

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RetryStrategy(str, Enum):
    """Retry strategy types"""

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""

    max_retries: int = 3
    initial_delay_seconds: int = 60
    max_delay_seconds: int = 3600  # 1 hour max
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    backoff_factor: float = 2.0
    jitter_factor: float = 0.1
    retryable_errors: list[str] | None = None

    def __post_init__(self):
        if self.retryable_errors is None:
            self.retryable_errors = [
                "timeout",
                "connection_error",
                "rate_limit",
                "service_unavailable",
                "internal_error",
            ]


class RetryManager:
    """Manages webhook retry scheduling and execution"""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self._pending_retries: dict[int, datetime] = {}
        self._retry_handlers: dict[str, Callable] = {}

    def calculate_next_retry_delay(self, retry_count: int) -> int:
        """Calculate delay before next retry based on strategy"""
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.initial_delay_seconds

        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.initial_delay_seconds * retry_count

        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.initial_delay_seconds * (  # type: ignore[assignment]
                self.config.backoff_factor ** (retry_count - 1)
            )

        elif self.config.strategy == RetryStrategy.EXPONENTIAL_JITTER:
            base_delay = self.config.initial_delay_seconds * (
                self.config.backoff_factor ** (retry_count - 1)
            )
            jitter = base_delay * self.config.jitter_factor * random.random()
            delay = base_delay + jitter  # type: ignore[assignment]

        else:
            delay = self.config.initial_delay_seconds

        # Cap at max delay
        return min(int(delay), self.config.max_delay_seconds)

    def should_retry(self, error: str, retry_count: int) -> bool:
        """Determine if a webhook should be retried"""
        if retry_count >= self.config.max_retries:
            logger.info("Max retries (%s) exceeded", self.config.max_retries)
            return False

        error_lower = error.lower()
        return any(
            retryable.lower() in error_lower
            for retryable in self.config.retryable_errors
        )

    def schedule_retry(self, webhook_log_id: int, retry_count: int) -> datetime:
        """Schedule a retry for a webhook"""
        delay_seconds = self.calculate_next_retry_delay(retry_count + 1)
        next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

        self._pending_retries[webhook_log_id] = next_retry_at

        logger.info(
            "Scheduled retry #%s for webhook %s at %s",
            retry_count + 1,
            webhook_log_id,
            next_retry_at,
        )
        return next_retry_at

    def cancel_retry(self, webhook_log_id: int) -> bool:
        """Cancel a scheduled retry"""
        if webhook_log_id in self._pending_retries:
            del self._pending_retries[webhook_log_id]
            logger.info("Cancelled retry for webhook %s", webhook_log_id)
            return True
        return False

    def get_pending_retries(self) -> dict[int, datetime]:
        """Get all pending retries"""
        return self._pending_retries.copy()

    def get_due_retries(self) -> list[int]:
        """Get webhook IDs that are due for retry"""
        now = datetime.now(UTC)
        return [
            webhook_id
            for webhook_id, retry_time in self._pending_retries.items()
            if retry_time <= now
        ]

    def register_retry_handler(self, source: str, handler: Callable) -> None:
        """Register a handler for retrying webhooks from a specific source"""
        self._retry_handlers[source] = handler
        logger.info("Registered retry handler for source '%s'", source)

    async def execute_retry(
        self,
        webhook_log_id: int,
        source: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Execute a retry for a webhook"""
        handler = self._retry_handlers.get(source)

        if not handler:
            logger.error("No retry handler registered for source '%s'", source)
            return {
                "success": False,
                "error": f"No retry handler for source '{source}'",
            }

        try:
            import inspect

            if inspect.iscoroutinefunction(handler):
                result = await handler(webhook_log_id, payload, headers)
            else:
                result = handler(webhook_log_id, payload, headers)

            # Remove from pending if successful
            if result.get("success"):
                self.cancel_retry(webhook_log_id)

            return result
        except Exception as e:
            logger.error("Retry handler failed for webhook %s: %s", webhook_log_id, e)
            return {"success": False, "error": str(e)}

    def get_retry_status(self, webhook_log_id: int) -> dict[str, Any] | None:
        """Get the retry status for a webhook"""
        if webhook_log_id not in self._pending_retries:
            return None

        retry_time = self._pending_retries[webhook_log_id]
        now = datetime.now(UTC)

        return {
            "webhook_log_id": webhook_log_id,
            "scheduled_for": retry_time.isoformat(),
            "seconds_until_retry": max(0, int((retry_time - now).total_seconds())),
            "is_due": retry_time <= now,
        }


# Global retry manager instance
retry_manager = RetryManager()
