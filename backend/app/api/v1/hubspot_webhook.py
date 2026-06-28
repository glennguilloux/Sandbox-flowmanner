"""HubSpot webhook handler — receives contact, deal, and ticket lifecycle events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hubspot", tags=["hubspot"])


def _verify_hubspot_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    method: str,
    uri: str,
) -> bool:
    """Verify HubSpot webhook signature (HMAC-SHA256 v3).

    HubSpot v3 concatenates: client_secret + HTTP_METHOD + URI + body,
    then HMAC-SHA256. Signature in X-HubSpot-Signature-v3 header.
    """
    if not sig_header:
        return False

    message = secret + method + uri + payload.decode("utf-8", errors="replace")
    expected = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, sig_header)


@router.post("/webhook")
async def hubspot_webhook(request: Request):
    """Handle HubSpot webhook events (contact/property changes, deal lifecycle)."""
    body = await request.body()

    # Verify HMAC-SHA256 v3 signature
    secret = settings.HUBSPOT_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-hubspot-signature-v3", "")
        uri = str(request.url)
        if not _verify_hubspot_signature(body, sig_header, secret, "POST", uri):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        events = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # HubSpot sends an array of subscription events
    if not isinstance(events, list):
        return {"status": "ok", "events": 0}

    for evt in events:
        subscription_type = evt.get("subscriptionType", "unknown")
        object_id = evt.get("objectId", "unknown")
        logger.info(
            "HubSpot webhook: subscriptionType=%s objectId=%s",
            subscription_type,
            object_id,
        )

    return {"status": "ok", "events": len(events)}
