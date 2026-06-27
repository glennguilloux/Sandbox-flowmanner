"""Integration Health Service — runs periodic health checks per integration.

Reads health-check config from integration manifests, calls lightweight
read-only endpoints, and stores results in ``IntegrationHealthRecord``.

The Celery beat task ``integration_health_check_all`` calls
``check_all()`` every 15 minutes.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from sqlalchemy import desc, select

from app.models.integration_models import IntegrationHealthRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class HealthResult:
    """Result of a single integration health check."""

    def __init__(
        self,
        status: str,
        latency_ms: int | None = None,
        status_code: int | None = None,
        error_message: str | None = None,
    ) -> None:
        self.status = status
        self.latency_ms = latency_ms
        self.status_code = status_code
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "latency_ms": self.latency_ms,
            "status_code": self.status_code,
            "error_message": self.error_message,
        }


class IntegrationHealthService:
    """Runs health checks for integrations and stores results."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check(self, slug: str, health_check_config: dict[str, Any]) -> HealthResult:
        """Run health check for a single integration using manifest config.

        Args:
            slug: Integration slug (e.g. "slack", "github").
            health_check_config: The ``health_check`` dict from the manifest.

        Returns:
            HealthResult with status, latency, status_code, and error.
        """
        endpoint = health_check_config.get("endpoint", "")
        method = health_check_config.get("method", "GET").upper()
        expected_status = health_check_config.get("expected_status", 200)
        timeout = health_check_config.get("timeout_seconds", 10)

        # Apiflow uses a relative path — skip it since we have no base URL
        if endpoint.startswith("/"):
            return HealthResult(
                status="unknown",
                error_message="Relative endpoint — requires user-specific base URL",
            )

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "POST":
                    resp = await client.post(endpoint)
                else:
                    resp = await client.get(endpoint)

            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code == expected_status:
                return HealthResult(
                    status="healthy",
                    latency_ms=latency_ms,
                    status_code=resp.status_code,
                )
            elif resp.status_code >= 500:
                return HealthResult(
                    status="down",
                    latency_ms=latency_ms,
                    status_code=resp.status_code,
                    error_message=f"HTTP {resp.status_code}",
                )
            else:
                # 4xx (e.g. 401 on unauthenticated health probes) — degraded
                return HealthResult(
                    status="degraded",
                    latency_ms=latency_ms,
                    status_code=resp.status_code,
                    error_message=f"HTTP {resp.status_code} (expected {expected_status})",
                )

        except httpx.TimeoutException:
            latency_ms = int((time.monotonic() - start) * 1000)
            return HealthResult(
                status="down",
                latency_ms=latency_ms,
                error_message=f"Timeout after {timeout}s",
            )
        except httpx.ConnectError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return HealthResult(
                status="down",
                latency_ms=latency_ms,
                error_message=f"Connection failed: {exc}",
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return HealthResult(
                status="down",
                latency_ms=latency_ms,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    async def check_and_store(self, slug: str, health_check_config: dict[str, Any]) -> HealthResult:
        """Run health check and persist the result to the DB."""
        result = await self.check(slug, health_check_config)
        await self._store(slug, result)
        return result

    async def check_all(self, health_checks: dict[str, dict[str, Any]]) -> dict[str, HealthResult]:
        """Run health checks for all integrations and store results."""
        results: dict[str, HealthResult] = {}
        for slug, config in health_checks.items():
            try:
                results[slug] = await self.check_and_store(slug, config)
            except Exception as exc:
                logger.error("Health check failed for %s: %s", slug, exc)
                results[slug] = HealthResult(status="unknown", error_message=str(exc))
        return results

    async def get_latest_status(self, slug: str) -> IntegrationHealthRecord | None:
        """Get the most recent health record for an integration."""
        result = await self.db.execute(
            select(IntegrationHealthRecord)
            .where(IntegrationHealthRecord.integration_slug == slug)
            .order_by(desc(IntegrationHealthRecord.checked_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all_latest(self) -> dict[str, IntegrationHealthRecord]:
        """Get the most recent health record for each integration.

        Uses PostgreSQL DISTINCT ON for efficient retrieval.
        """
        from sqlalchemy import desc

        result = await self.db.execute(
            select(IntegrationHealthRecord)
            .distinct(IntegrationHealthRecord.integration_slug)
            .order_by(
                IntegrationHealthRecord.integration_slug,
                desc(IntegrationHealthRecord.checked_at),
            )
        )
        records = result.scalars().all()
        return {r.integration_slug: r for r in records}

    async def get_history(self, slug: str, limit: int = 50) -> list[IntegrationHealthRecord]:
        """Get recent health check history for an integration."""
        result = await self.db.execute(
            select(IntegrationHealthRecord)
            .where(IntegrationHealthRecord.integration_slug == slug)
            .order_by(desc(IntegrationHealthRecord.checked_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def compute_uptime_pct(self, slug: str, days: int = 30) -> float | None:
        """Compute uptime percentage over the given window.

        Returns None if no records exist.
        """
        from datetime import timedelta

        from sqlalchemy import func

        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(
            select(
                func.count().label("total"),
                func.count().filter(IntegrationHealthRecord.status == "healthy").label("healthy"),
            ).where(
                IntegrationHealthRecord.integration_slug == slug,
                IntegrationHealthRecord.checked_at >= cutoff,
            )
        )
        row = result.one()
        if row.total == 0:
            return None
        return round((row.healthy / row.total) * 100, 1)

    async def record_failure(self, slug: str, error_message: str) -> None:
        """Record an integration failure from runtime usage (circuit breaker hook).

        Called by the integration bridge/executor when an outbound call
        fails, providing real-time health updates between periodic checks.
        """
        await self._store(
            slug,
            HealthResult(status="degraded", error_message=error_message),
        )
        logger.warning("Integration %s degraded: %s", slug, error_message)

    async def record_outage(self, slug: str, error_message: str) -> None:
        """Record a hard outage (circuit breaker opened)."""
        await self._store(
            slug,
            HealthResult(status="down", error_message=error_message),
        )
        logger.error("Integration %s DOWN: %s", slug, error_message)

    # ── Internal helpers ────────────────────────────────────────────────

    async def _store(self, slug: str, result: HealthResult) -> None:
        """Persist a health check result."""
        record = IntegrationHealthRecord(
            id=str(uuid4()),
            integration_slug=slug,
            status=result.status,
            latency_ms=result.latency_ms,
            status_code=result.status_code,
            error_message=result.error_message,
            checked_at=datetime.now(UTC),
        )
        self.db.add(record)
        await self.db.flush()

    async def cleanup_old_records(self, days: int = 90) -> int:
        """Delete health records older than *days* days.

        Called periodically to prevent unbounded table growth.
        Returns the number of deleted rows.
        """
        from datetime import timedelta

        from sqlalchemy import delete

        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(
            delete(IntegrationHealthRecord).where(IntegrationHealthRecord.checked_at < cutoff)
        )
        return result.rowcount  # type: ignore[return-value]
