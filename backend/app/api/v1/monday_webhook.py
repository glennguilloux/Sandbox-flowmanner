"""
Monday.com Webhook Handler

Receives webhook events from Monday.com.
Monday.com does not use standard HMAC verification — security via tokens in URL or IP whitelisting.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monday-webhook"])


@router.post("/monday/webhook")
async def monday_webhook(request: Request):
    """Handle incoming Monday.com webhook events."""
    body = await request.body()

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Monday.com sends a challenge during webhook setup
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    event_type = payload.get("event", {}).get("type", "unknown")
    logger.info("Monday.com webhook: type=%s", event_type)

    return {"status": "ok", "type": event_type}
