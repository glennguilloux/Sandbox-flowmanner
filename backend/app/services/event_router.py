"""Event router — bridges integration webhooks to the trigger system.

**Thin facade.**  This module is a convenience wrapper over
the durable ``EventBus`` (``app.services.event_bus``).  New code should call
``get_event_bus().publish()`` directly.  ``emit_integration_event()`` is
preserved so that the 21 webhook handlers already calling it continue to work
without modification — it delegates to ``EventBus.publish()`` which:

1. Persists the event as an ``ExternalEvent`` (append-only, idempotent).
2. Dispatches to registered consumers (trigger matching, future: audit, analytics).
3. Returns the persisted event with processing status.

This is the durable "ignition" that connects 21+ integration webhooks to the
execution substrate, with full replay and observability.

Usage (from any webhook handler — unchanged):

    from app.services.event_router import emit_integration_event

    await emit_integration_event(
        db=db,
        source="sentry",
        event_type="issue.created",
        user_id=user_id,          # if known
        payload={"issue": {...}},
        delivery_id="abc-123",    # for idempotency
    )

Trigger matching:
- A ``MissionTrigger`` with ``trigger_type == "webhook"`` and
  ``config.integration == "sentry"`` matches ALL Sentry events.
- Adding ``config.event_types == ["issue.created", "issue.regression"]``
  narrows to specific event types.
- If no ``config.integration`` is set, the trigger is a generic webhook
  trigger (matched by ``webhook_path``) and is NOT matched by this router.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Canonical event shape (preserved for backward compat) ──────────────


@dataclass
class IntegrationEvent:
    """Normalized event from an external integration webhook."""

    source: str  # e.g. "sentry", "stripe", "pagerduty"
    event_type: str  # e.g. "issue.created", "charge.failed"
    payload: dict[str, Any] = field(default_factory=dict)
    user_id: int | None = None
    raw_body: dict[str, Any] | None = None


# ── Public API ──────────────────────────────────────────────────────────


async def emit_integration_event(
    db: AsyncSession,
    *,
    source: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    user_id: int | None = None,
    raw_body: dict[str, Any] | None = None,
    delivery_id: str | None = None,
) -> str:
    """Emit an integration event via the durable EventBus.

    This is a thin convenience wrapper over ``EventBus.publish()``.
    The event is persisted as an ``ExternalEvent`` row *before* any
    triggers are fired, giving durability, idempotency, and replay.

    Dispatch (trigger matching, audit, failure alerts) runs OFF the request
    path in the ``process_external_event`` Celery task, which the calling
    webhook route enqueues after its DB transaction commits.

    Args:
        db: Database session (caller owns the transaction).
        source: Integration source slug (e.g. "sentry", "stripe").
        event_type: Normalized event type (e.g. "issue.created").
        payload: Structured event data.
        user_id: User ID if known from the webhook context.
        raw_body: Raw webhook body for debugging.
        delivery_id: Idempotency key (e.g. Stripe event ID, GitHub delivery GUID).

    Returns:
        The persisted ``ExternalEvent`` id (str).  Trigger dispatch is
        asynchronous — callers must not assume ``triggers_fired`` is populated
        on return.
    """
    # If no natural delivery_id was provided, generate a synthetic one
    # from HMAC(source:event_type:sorted_payload_json) so duplicate webhook
    # deliveries are detected even for integrations that don't send a
    # delivery identifier (PagerDuty, GitLab, Jira, etc.).
    if not delivery_id and payload:
        delivery_id = _synthetic_delivery_id(source, event_type, payload)

    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    event = await bus.publish(
        db,
        source=source,
        event_type=event_type,
        payload=payload,
        raw_body=raw_body,
        delivery_id=delivery_id,
        user_id=user_id,
    )

    # Dispatch happens asynchronously in the Celery process_external_event task.
    # Return the event id so callers can correlate / await if needed.
    return str(event.id)


# ── Synthetic delivery_id ───────────────────────────────────────────

# Fixed key for HMAC — not a secret, just a domain separator to avoid
# collisions with other HMAC uses in the codebase.
_SYNTHETIC_KEY = b"flowmanner.external-event.v1"


def _synthetic_delivery_id(source: str, event_type: str, payload: dict[str, Any]) -> str:
    """Generate a deterministic delivery_id from source + event_type + payload.

    Uses HMAC-SHA256 to produce a hex digest.  The payload is JSON-serialized
    with sorted keys so the same logical payload always produces the same hash.
    Returns a 32-char hex prefix (128 bits) — plenty for collision avoidance.
    """
    # Sort keys for determinism, compact for speed
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    message = f"{source}:{event_type}:{body}".encode()
    digest = hmac.new(_SYNTHETIC_KEY, message, hashlib.sha256).hexdigest()
    return f"syn:{digest[:32]}"
