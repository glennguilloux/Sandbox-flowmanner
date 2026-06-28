"""Asana webhook handler — receives task and project lifecycle events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asana", tags=["asana"])


def _verify_asana_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Asana webhook signature (HMAC-SHA256).

    Asana sends the signature in the X-Hook-Signature header as a hex digest.
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
async def asana_webhook(request: Request):
    """Handle Asana webhook events (task lifecycle, project changes)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.ASANA_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-hook-signature", "")
        if not _verify_asana_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Asana webhook handshake: respond to GET challenge
    if "challenge" in event:
        return {"challenge": event["challenge"]}

    events = event.get("events", [])
    if not events:
        return {"status": "ok", "events": 0}

    for evt in events:
        action = evt.get("action", "unknown")
        resource = evt.get("resource", {})
        resource_type = resource.get("resource_type", "unknown")
        logger.info(
            "Asana webhook: action=%s resource_type=%s resource_gid=%s",
            action,
            resource_type,
            resource.get("gid", "unknown"),
        )

    return {"status": "ok", "events": len(events)}
