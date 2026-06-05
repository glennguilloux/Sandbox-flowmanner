"""Analytics tracking service."""

import logging
from typing import Any

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
