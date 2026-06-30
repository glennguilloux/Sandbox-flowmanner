"""EventBus consumers — process inbound ExternalEvents.

Each consumer is an async callable with the signature::

    async def my_consumer(db: AsyncSession, event: ExternalEvent) -> None

Consumers are registered on the EventBus singleton and called in order
after each event is persisted.  A consumer failure does NOT prevent
subsequent consumers from running (isolation).

Default consumers:
- ``trigger_matching_consumer`` — fires matching MissionTrigger rows
  (the existing event_router logic, now wrapped as a consumer).

Future consumers (stubs below for reference):
- ``audit_log_consumer`` — writes to workspace_activity_log
- ``analytics_consumer`` — tracks integration event metrics
- ``ai_learning_consumer`` — feeds events to the memory flywheel
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select

from app.models.trigger_models import MissionTrigger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.external_event_model import ExternalEvent

logger = logging.getLogger(__name__)


# ── Trigger matching consumer (production) ─────────────────────────


async def trigger_matching_consumer(
    db: AsyncSession,
    event: ExternalEvent,
) -> None:
    """Fire all MissionTrigger rows whose config matches the event.

    This is the core of the activation layer: it converts an inbound
    ``ExternalEvent`` into one or more trigger fires, which in turn
    launch workflows via the UnifiedExecutor.

    Matching criteria (same as the old ``event_router._find_matching_triggers``):
    - ``trigger_type == "webhook"``
    - ``status == "active"``
    - ``is_deleted == False``
    - ``config.integration == event.source``
    - If ``config.event_types`` is set, ``event.event_type`` must be in the list.
    - If ``event.user_id`` is set, ``trigger.user_id`` must match.
    """
    from app.services import trigger_service as svc

    triggers = await _find_matching_triggers(db, event)
    if not triggers:
        logger.debug(
            "event_bus: no matching triggers for %s.%s (event %s)",
            event.source,
            event.event_type,
            event.id,
        )
        return

    fired = 0
    for trigger in triggers:
        try:
            await svc.fire_trigger(
                db,
                trigger,
                payload={
                    "source": "integration",
                    "integration": event.source,
                    "event_type": event.event_type,
                    "event_data": event.payload or {},
                    "external_event_id": str(event.id),
                },
            )
            fired += 1
            logger.info(
                "event_bus: fired trigger %s for %s.%s (event %s)",
                trigger.id,
                event.source,
                event.event_type,
                event.id,
            )
        except Exception:
            logger.warning(
                "event_bus: failed to fire trigger %s for %s.%s (event %s)",
                trigger.id,
                event.source,
                event.event_type,
                event.id,
                exc_info=True,
            )

    event.triggers_fired = fired
    if fired:
        logger.info(
            "event_bus: %s.%s → %d trigger(s) fired (event %s)",
            event.source,
            event.event_type,
            fired,
            event.id,
        )


async def _find_matching_triggers(
    db: AsyncSession,
    event: ExternalEvent,
) -> list[MissionTrigger]:
    """Find active webhook triggers whose config matches the event.

    Identical logic to ``event_router._find_matching_triggers`` but
    accepts an ``ExternalEvent`` instead of ``IntegrationEvent``.
    """
    conditions = [
        MissionTrigger.trigger_type == "webhook",
        MissionTrigger.status == "active",
        MissionTrigger.is_deleted == False,
    ]

    if event.user_id is not None:
        conditions.append(MissionTrigger.user_id == event.user_id)

    result = await db.execute(select(MissionTrigger).where(and_(*conditions)))
    all_webhook_triggers = list(result.scalars().all())

    matched: list[MissionTrigger] = []
    for trigger in all_webhook_triggers:
        cfg: dict[str, Any] = trigger.config or {}

        integration = cfg.get("integration")
        if not integration:
            continue

        if integration != event.source:
            continue

        allowed_types = cfg.get("event_types")
        if allowed_types and event.event_type not in allowed_types:
            continue

        matched.append(trigger)

    return matched


# ── Audit log consumer (compliance) ────────────────────────────────


async def audit_log_consumer(
    db: AsyncSession,
    event: ExternalEvent,
) -> None:
    """Write an ExternalEvent summary to workspace_activity_log.

    Provides a compliance-grade audit trail of every inbound integration
    event, scoped to the user's workspace.  If no workspace can be resolved
    (e.g. system-wide events with no user_id), the audit entry is skipped
    gracefully — never blocks the event pipeline.

    Activity log shape:
    - action: ``integration.event.received``
    - target_type: ``external_event``
    - target_id: ExternalEvent UUID
    - metadata: source, event_type, triggers_fired, status, delivery_id
    """
    if event.user_id is None:
        # No user context — cannot resolve workspace.  Skip silently.
        return

    workspace_id = await _resolve_workspace(db, event.user_id)
    if workspace_id is None:
        logger.debug(
            "audit_log_consumer: no workspace found for user %s (event %s)",
            event.user_id,
            event.id,
        )
        return

    from uuid import uuid4

    from app.models.workspace_activity_log import WorkspaceActivityLog

    entry = WorkspaceActivityLog(
        id=str(uuid4()),
        workspace_id=workspace_id,
        actor_id=event.user_id,
        action="integration.event.received",
        target_type="external_event",
        target_id=str(event.id),
        activity_metadata={
            "source": event.source,
            "event_type": event.event_type,
            "delivery_id": event.delivery_id,
            "triggers_fired": event.triggers_fired,
            "status": event.status,
        },
    )
    db.add(entry)
    # No flush/commit — the caller owns the transaction.

    logger.debug(
        "audit_log_consumer: logged %s.%s for workspace %s (event %s)",
        event.source,
        event.event_type,
        workspace_id,
        event.id,
    )


async def _resolve_workspace(db: AsyncSession, user_id: int) -> str | None:
    """Resolve a user's workspace_id via the workspace_members table.

    Returns the first workspace the user belongs to, or None if the user
    has no workspace membership.
    """
    from app.models.workspace_models import WorkspaceMember

    result = await db.execute(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id).limit(1))
    row = result.first()
    return row[0] if row else None


# ── Failure alert consumer (real-time Slack + PagerDuty) ──────────


async def failure_alert_consumer(
    db: AsyncSession,
    event: ExternalEvent,
) -> None:
    """Send real-time alerts when an ExternalEvent fails processing.

    Registered as a *failure handler* (runs only when ``event.status == "failed"``).
    Dispatches to Slack (incoming webhook) and/or PagerDuty (Events API v2)
    based on available configuration.  Both channels are fire-and-forget:
    delivery failures are logged as warnings but never block the event pipeline.

    Configuration (env vars / ``app.config.settings``):
    - ``SLACK_ALERT_WEBHOOK_URL`` — Slack incoming webhook URL for failure alerts.
    - ``PAGERDUTY_ALERT_ROUTING_KEY`` — PagerDuty Events API v2 routing key.
    """
    import httpx

    from app.config import settings

    summary = (
        f"⚠️ Integration event failed: {event.source}.{event.event_type}\n"
        f"Event ID: {event.id}\n"
        f"Error: {event.error_message or 'Unknown'}\n"
        f"Triggers fired: {event.triggers_fired}"
    )

    # ── Slack ──────────────────────────────────────────────────────
    slack_url = getattr(settings, "SLACK_ALERT_WEBHOOK_URL", None)
    if slack_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    slack_url,
                    json={
                        "text": summary,
                        "blocks": [
                            {
                                "type": "header",
                                "text": {
                                    "type": "plain_text",
                                    "text": f"🚨 Integration Event Failed: {event.source}",
                                },
                            },
                            {
                                "type": "section",
                                "fields": [
                                    {"type": "mrkdwn", "text": f"*Source:*\n{event.source}"},
                                    {"type": "mrkdwn", "text": f"*Event Type:*\n{event.event_type}"},
                                    {"type": "mrkdwn", "text": f"*Event ID:*\n`{event.id}`"},
                                    {"type": "mrkdwn", "text": f"*Triggers Fired:*\n{event.triggers_fired}"},
                                ],
                            },
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"*Error:*\n```{event.error_message or 'Unknown'}```",
                                },
                            },
                        ],
                    },
                )
                if resp.status_code < 300:
                    logger.info("failure_alert: Slack alert sent for event %s", event.id)
                else:
                    logger.warning(
                        "failure_alert: Slack returned %d for event %s",
                        resp.status_code,
                        event.id,
                    )
        except Exception:
            logger.warning(
                "failure_alert: Slack delivery failed for event %s",
                event.id,
                exc_info=True,
            )

    # ── PagerDuty ──────────────────────────────────────────────────
    pd_key = getattr(settings, "PAGERDUTY_ALERT_ROUTING_KEY", None)
    if pd_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json={
                        "routing_key": pd_key,
                        "event_action": "trigger",
                        "payload": {
                            "summary": (f"Integration event failed: {event.source}.{event.event_type}"),
                            "source": "flowmanner-event-bus",
                            "severity": "warning",
                            "custom_details": {
                                "event_id": str(event.id),
                                "source": event.source,
                                "event_type": event.event_type,
                                "delivery_id": event.delivery_id,
                                "error_message": event.error_message,
                                "triggers_fired": event.triggers_fired,
                            },
                        },
                    },
                )
                if resp.status_code < 300:
                    logger.info("failure_alert: PagerDuty alert sent for event %s", event.id)
                else:
                    logger.warning(
                        "failure_alert: PagerDuty returned %d for event %s",
                        resp.status_code,
                        event.id,
                    )
        except Exception:
            logger.warning(
                "failure_alert: PagerDuty delivery failed for event %s",
                event.id,
                exc_info=True,
            )

    if not slack_url and not pd_key:
        logger.debug(
            "failure_alert: no SLACK_ALERT_WEBHOOK_URL or PAGERDUTY_ALERT_ROUTING_KEY configured — skipping alert for event %s",
            event.id,
        )


# ── Future consumers (stubs) ───────────────────────────────────────
#
# Uncomment and implement as needed:
#
# async def analytics_consumer(db: AsyncSession, event: ExternalEvent) -> None:
#     """Track integration event metrics (counts, latencies, error rates)."""
#     pass
#
# async def ai_learning_consumer(db: AsyncSession, event: ExternalEvent) -> None:
#     """Feed events to the memory flywheel / learning loop."""
#     pass
