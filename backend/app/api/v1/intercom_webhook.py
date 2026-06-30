"""Intercom webhook handler — receives conversation and contact lifecycle events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intercom", tags=["intercom"])


def _verify_intercom_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Intercom webhook signature (HMAC-SHA256).

    Intercom uses a hub signature style: HMAC-SHA256 of the raw body
    using the client secret. The signature is sent in the
    X-Hub-Signature-256 header as 'sha256=<hex>'.
    """
    if not sig_header:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Intercom sends signature as "sha256=<hex>"
    sig_value = sig_header[7:] if sig_header.startswith("sha256=") else sig_header

    return hmac.compare_digest(expected, sig_value)


@router.post("/webhook")
async def intercom_webhook(request: Request):
    """Handle Intercom webhook events (conversation, contact lifecycle)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.INTERCOM_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-hub-signature-256", "")
        if not _verify_intercom_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type", "unknown")
    topic = event.get("topic", "unknown")
    logger.info("Intercom webhook received: type=%s topic=%s", event_type, topic)

    # Log events for agent triage
    data = event.get("data", {}).get("item", {})

    if "conversation" in topic:
        logger.info(
            "Intercom conversation event: %s — conversation %s",
            topic,
            data.get("id", "unknown"),
        )
    elif "contact" in topic:
        logger.info(
            "Intercom contact event: %s — contact %s",
            topic,
            data.get("id", "unknown"),
        )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="intercom",
                event_type=topic,
                payload={
                    "type": event_type,
                    "topic": topic,
                    "item_id": data.get("id"),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("Intercom event router failed for %s", topic, exc_info=True)

    return {"status": "ok", "topic": topic}
