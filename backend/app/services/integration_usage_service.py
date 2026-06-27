"""Integration Usage Service — tracks and aggregates per-user integration usage.

Records each integration action execution via ``record_call()`` and provides
aggregated analytics via ``get_usage_stats()`` for the frontend usage dashboard.

The service is used by:
- ``action_registry.execute_action()`` — logs every action call.
- ``GET /api/v1/integrations/{slug}/usage`` — returns aggregated stats.
- Retention cleanup runs alongside the health-check Celery task.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import delete, desc, func, select

from app.models.integration_models import IntegrationUsageLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Period definitions for the usage API
_PERIOD_DELTAS: dict[str, timedelta] = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


class IntegrationUsageService:
    """Tracks and queries per-user integration usage analytics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Recording ────────────────────────────────────────────────────────

    async def record_call(
        self,
        *,
        user_id: int,
        integration_slug: str,
        action: str | None = None,
        status: str = "success",
        status_code: int | None = None,
        latency_ms: int | None = None,
        error_message: str | None = None,
    ) -> IntegrationUsageLog:
        """Record a single integration action execution.

        Called by ``action_registry.execute_action()`` after each attempt.
        """
        log = IntegrationUsageLog(
            id=str(uuid4()),
            user_id=user_id,
            integration_slug=integration_slug,
            action=action,
            status=status,
            status_code=status_code,
            latency_ms=latency_ms,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )
        self.db.add(log)
        await self.db.flush()
        return log

    # ── Querying ─────────────────────────────────────────────────────────

    async def get_usage_stats(
        self,
        *,
        user_id: int,
        integration_slug: str,
        period: str = "30d",
    ) -> dict[str, Any]:
        """Return aggregated usage stats for a user's integration.

        Returns a dict with:
            - total_calls, successful_calls, failed_calls
            - avg_latency_ms, p95_latency_ms
            - last_activity (ISO timestamp)
            - top_actions (list of {action, count})
        """
        delta = _PERIOD_DELTAS.get(period, timedelta(days=30))
        cutoff = datetime.now(UTC) - delta

        # Base filter
        base = select(IntegrationUsageLog).where(
            IntegrationUsageLog.user_id == user_id,
            IntegrationUsageLog.integration_slug == integration_slug,
            IntegrationUsageLog.created_at >= cutoff,
        )

        # Aggregate counts
        count_result = await self.db.execute(
            select(
                func.count().label("total"),
                func.count().filter(IntegrationUsageLog.status == "success").label("successful"),
                func.count().filter(IntegrationUsageLog.status != "success").label("failed"),
                func.avg(IntegrationUsageLog.latency_ms).label("avg_latency"),
                func.percentile_cont(0.95).within_group(IntegrationUsageLog.latency_ms).label("p95_latency"),
            ).where(
                IntegrationUsageLog.user_id == user_id,
                IntegrationUsageLog.integration_slug == integration_slug,
                IntegrationUsageLog.created_at >= cutoff,
            )
        )
        row = count_result.one()

        # Last activity
        last_result = await self.db.execute(
            select(IntegrationUsageLog.created_at)
            .where(
                IntegrationUsageLog.user_id == user_id,
                IntegrationUsageLog.integration_slug == integration_slug,
            )
            .order_by(desc(IntegrationUsageLog.created_at))
            .limit(1)
        )
        last_activity = last_result.scalar()

        # Top actions
        top_actions_result = await self.db.execute(
            select(
                IntegrationUsageLog.action,
                func.count().label("count"),
            )
            .where(
                IntegrationUsageLog.user_id == user_id,
                IntegrationUsageLog.integration_slug == integration_slug,
                IntegrationUsageLog.created_at >= cutoff,
                IntegrationUsageLog.action.isnot(None),
            )
            .group_by(IntegrationUsageLog.action)
            .order_by(desc("count"))
            .limit(10)
        )
        top_actions = [{"action": r.action, "count": r.count} for r in top_actions_result.all()]

        total = row.total or 0
        return {
            "integration": integration_slug,
            "period": period,
            "total_calls": total,
            "successful_calls": row.successful or 0,
            "failed_calls": row.failed or 0,
            "success_rate": round((row.successful or 0) / total * 100, 1) if total > 0 else 0.0,
            "avg_latency_ms": round(row.avg_latency) if row.avg_latency else None,
            "p95_latency_ms": round(row.p95_latency) if row.p95_latency else None,
            "last_activity": last_activity.isoformat() if last_activity else None,
            "top_actions": top_actions,
        }

    # ── Retention ────────────────────────────────────────────────────────

    async def cleanup_old_records(self, days: int = 90) -> int:
        """Delete usage logs older than *days* days.

        Called periodically (alongside health record cleanup) to prevent
        unbounded table growth.  Returns the number of deleted rows.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(delete(IntegrationUsageLog).where(IntegrationUsageLog.created_at < cutoff))
        return result.rowcount  # type: ignore[return-value]
