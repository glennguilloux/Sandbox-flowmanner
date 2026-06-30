"""Stripe webhook handler — receives payment/subscription lifecycle events."""

import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["stripe"])


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe webhook signature (HMAC-SHA256).

    Stripe-Signature format: t={timestamp},v1={signature}
    We compute HMAC-SHA256 of '{timestamp}.{body}' using the webhook signing secret.
    Rejects if timestamp is older than 5 minutes (replay protection).
    """
    if not sig_header:
        return False

    parts: dict[str, str] = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()

    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False

    # Replay protection: reject timestamps older than 5 minutes
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            logger.warning("Stripe webhook timestamp too old: %s", timestamp)
            return False
    except ValueError:
        return False

    # Compute expected signature
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (charges, invoices, subscriptions)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.STRIPE_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("stripe-signature", "")
        if not _verify_stripe_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type", "unknown")
    logger.info("Stripe webhook received: %s", event_type)

    # Log events for agent triage
    data_object = event.get("data", {}).get("object", {})

    if event_type.startswith("charge."):
        logger.info(
            "Stripe charge event: %s — charge %s, amount: %s %s",
            event_type,
            data_object.get("id", "unknown"),
            data_object.get("amount", "?"),
            data_object.get("currency", "?"),
        )
    elif event_type.startswith("invoice."):
        logger.info(
            "Stripe invoice event: %s — invoice %s, customer: %s",
            event_type,
            data_object.get("id", "unknown"),
            data_object.get("customer", "unknown"),
        )
    elif event_type.startswith("customer.subscription."):
        logger.info(
            "Stripe subscription event: %s — subscription %s, status: %s",
            event_type,
            data_object.get("id", "unknown"),
            data_object.get("status", "unknown"),
        )

    # Route through the event router → trigger system → UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="stripe",
                event_type=event_type,
                payload={
                    "event_id": event.get("id"),
                    "object_id": data_object.get("id"),
                    "amount": data_object.get("amount"),
                    "currency": data_object.get("currency"),
                    "customer": data_object.get("customer"),
                    "status": data_object.get("status"),
                },
                raw_body=event,
                delivery_id=event.get("id"),
            )
            await event_db.commit()
    except Exception:
        logger.warning("Stripe event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "event_type": event_type}
