"""Datadog webhook handler — receives monitor alert events from Datadog."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datadog", tags=["datadog"])


def _verify_datadog_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Datadog webhook signature (HMAC-SHA256).

    Datadog sends the signature in the X-Datadog-Signature header.
    Compute HMAC-SHA256 of raw body using webhook secret, compare with header.
    """
    if not sig_header:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, sig_header)


@router.post("/webhook")
async def datadog_webhook(request: Request):
    """Handle Datadog webhook events (monitor alerts)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.DATADOG_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-datadog-signature", "")
        if not _verify_datadog_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("event_type", event.get("alert_type", "unknown"))
    logger.info("Datadog webhook received: %s", event_type)

    # Log monitor events for agent triage
    title = event.get("title", event.get("event_title", "no title"))
    logger.info(
        "Datadog event: %s — %s",
        event_type,
        title,
    )

    return {"status": "ok", "event_type": event_type}
