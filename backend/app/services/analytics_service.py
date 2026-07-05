"""Analytics tracking service."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Event types
class EventType:
    ACCOUNT_CREATED = "account_created"
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_EXECUTED_SUCCESS = "workflow_executed_success"
    WORKFLOW_EXECUTED_FAILED = "workflow_executed_failed"
    TEMPLATE_USED = "template_used"
    INTEGRATION_CONNECTED = "integration_connected"
    INVITE_SENT = "invite_sent"
    INVITE_ACCEPTED = "invite_accepted"
    SURVEY_SHOWN = "survey_shown"
    SURVEY_RESPONSE = "survey_response"


async def track_event(
    db: AsyncSession,
    user_id: str,
    event_type: str,
    properties: dict[str, Any] | None = None,
    session_id: str | None = None,
):
    """Track an analytics event. Fire-and-forget — never raises."""
    try:
        from app.models.analytics import AnalyticsEvent

        event = AnalyticsEvent(
            user_id=user_id,
            event_type=event_type,
            properties=properties or {},
            session_id=session_id,
        )
        db.add(event)
        await db.commit()
    except Exception as e:
        logger.warning("Failed to track analytics event %s: %s", event_type, e)
        await db.rollback()


async def get_tool_call_metrics(
    db: AsyncSession,
    workspace_id: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Aggregate tool-call counts, average duration, and total cost.

    Returns one row per tool_name with call_count, avg_duration_ms, total_cost_usd.
    Filters to ``cost_category = 'tool_execution'`` in the LLMCallRecord table.
    """
    from datetime import timedelta

    from sqlalchemy import func

    from app.models.llm_call_record import LLMCallRecord

    cutoff = func.now() - timedelta(days=days)

    query = (
        select(
            LLMCallRecord.tool_name,
            func.count().label("call_count"),
            func.avg(LLMCallRecord.latency_ms).label("avg_duration_ms"),
            func.sum(LLMCallRecord.cost_usd).label("total_cost_usd"),
        )
        .where(
            LLMCallRecord.cost_category == "tool_execution",
            LLMCallRecord.timestamp >= cutoff,
        )
        .group_by(LLMCallRecord.tool_name)
    )

    if workspace_id:
        query = query.where(LLMCallRecord.workspace_id == workspace_id)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "tool_name": row.tool_name,
            "call_count": row.call_count,
            "avg_duration_ms": float(row.avg_duration_ms or 0),
            "total_cost_usd": float(row.total_cost_usd or 0),
        }
        for row in rows
    ]


async def track_events_batch(
    db: AsyncSession,
    events: list[dict],
):
    """Track multiple events at once."""
    try:
        from app.models.analytics import AnalyticsEvent

        for event_data in events:
            event = AnalyticsEvent(
                user_id=event_data["user_id"],
                event_type=event_data["event_type"],
                properties=event_data.get("properties", {}),
                session_id=event_data.get("session_id"),
            )
            db.add(event)
        await db.commit()
    except Exception as e:
        logger.warning("Failed to track analytics batch: %s", e)
        await db.rollback()
