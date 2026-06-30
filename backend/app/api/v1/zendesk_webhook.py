"""
Zendesk Webhook Handler

Receives webhook events from Zendesk.
Signature verification: X-Zendesk-Webhook-Signation header.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["zendesk-webhook"])


@router.post("/zendesk/webhook")
async def zendesk_webhook(
    request: Request,
    x_zendesk_webhook_signature: str = Header(None),
):
    """Handle incoming Zendesk webhook events."""
    body = await request.body()

    # Verify webhook signature
    if settings.ZENDESK_WEBHOOK_SECRET and x_zendesk_webhook_signature:
        computed = hashlib.sha256((settings.ZENDESK_WEBHOOK_SECRET + body.decode()).encode()).hexdigest()
        if not hmac.compare_digest(computed, x_zendesk_webhook_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    import json

    try:
        payload = json.loads(body)
    except Exception:
        payload = {}

    event_type = payload.get("type", "unknown")
    logger.info("Zendesk webhook: type=%s", event_type)

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="zendesk",
                event_type=event_type,
                payload={
                    "type": event_type,
                    "ticket_id": payload.get("ticket", {}).get("id"),
                    "ticket_subject": payload.get("ticket", {}).get("subject"),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("Zendesk event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "type": event_type}
