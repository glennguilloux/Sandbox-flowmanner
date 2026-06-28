"""PagerDuty webhook handler — receives incident lifecycle events from PagerDuty."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pagerduty", tags=["pagerduty"])


def _verify_pagerduty_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify PagerDuty webhook V3 signature (HMAC-SHA256).

    Signature in X-PagerDuty-Signature header.
    Compute HMAC-SHA256 of raw body using webhook secret, compare with header.
    """
    if not sig_header:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # PagerDuty sends signature as "v1=<hex>"
    sig_value = sig_header[3:] if sig_header.startswith("v1=") else sig_header

    return hmac.compare_digest(expected, sig_value)


@router.post("/webhook")
async def pagerduty_webhook(request: Request):
    """Handle PagerDuty webhook events (incident triggered, acknowledged, resolved)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.PAGERDUTY_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-pagerduty-signature", "")
        if not _verify_pagerduty_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # PagerDuty V3 webhooks send an array of events
    events = event if isinstance(event, list) else [event]

    for evt in events:
        event_type = evt.get("event", {}).get("event_type", evt.get("type", "unknown"))
        logger.info("PagerDuty webhook received: %s", event_type)

        # Log incident events for agent triage
        incident = evt.get("event", {}).get("data", evt.get("incident", {}))
        if incident:
            logger.info(
                "PagerDuty incident event: %s — incident %s, title: %s, status: %s",
                event_type,
                incident.get("id", "unknown"),
                incident.get("title", "no title"),
                incident.get("status", "unknown"),
            )

    return {"status": "ok", "events_processed": len(events)}
