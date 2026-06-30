"""Slack webhook handler — receives events via the Slack Events API.

Handles Slack's URL verification challenge during setup and routes
all other events through the event router to the trigger system.

Slack Events API docs: https://api.slack.com/apis/events-api
"""

import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])


def _verify_slack_signature(
    body: bytes,
    sig_header: str,
    secret: str,
    timestamp: str,
) -> bool:
    """Verify Slack request signature (HMAC-SHA256).

    Slack computes: HMAC-SHA256('v0:' + timestamp + ':' + raw_body)
    using the signing secret. The signature is in X-Slack-Signature
    header as 'v0=<hex>'.

    Also rejects requests older than 5 minutes (replay protection).
    """
    if not sig_header or not timestamp:
        return False

    # Replay protection: reject timestamps older than 5 minutes
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            logger.warning("Slack webhook timestamp too old: %s", timestamp)
            return False
    except ValueError:
        return False

    basestring = f"v0:{timestamp}:{body.decode('utf-8', errors='replace')}"
    expected = (
        "v0="
        + hmac.new(
            secret.encode("utf-8"),
            basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(expected, sig_header)


@router.post("/webhook")
async def slack_webhook(request: Request):
    """Handle Slack Events API webhook.

    Supports:
    - url_verification challenge (setup)
    - event_callback (all Slack events: message, app_mention, etc.)
    """
    body = await request.body()

    # Verify signature
    secret = settings.SLACK_SIGNING_SECRET
    if secret:
        sig_header = request.headers.get("x-slack-signature", "")
        timestamp = request.headers.get("x-slack-request-timestamp", "")
        if not _verify_slack_signature(body, sig_header, secret, timestamp):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Handle URL verification challenge (Slack setup requirement)
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge", "")
        logger.info("Slack URL verification challenge received")
        return {"challenge": challenge}

    # Handle event callbacks
    if payload.get("type") != "event_callback":
        logger.warning("Slack webhook: unknown type=%s", payload.get("type"))
        return {"status": "ok", "type": "ignored"}

    event = payload.get("event", {})
    event_type = event.get("type", "unknown")
    team_id = payload.get("team_id", "unknown")
    api_app_id = payload.get("api_app_id", "unknown")

    logger.info(
        "Slack event received: type=%s team=%s app=%s",
        event_type,
        team_id,
        api_app_id,
    )

    # Log specific event types
    if event_type == "message":
        channel = event.get("channel", "unknown")
        user = event.get("user", "unknown")
        text = event.get("text", "")[:100]
        logger.info("Slack message in %s from %s: %s", channel, user, text)
    elif event_type == "app_mention":
        channel = event.get("channel", "unknown")
        user = event.get("user", "unknown")
        text = event.get("text", "")[:100]
        logger.info("Slack app_mention in %s from %s: %s", channel, user, text)
    elif event_type in ("reaction_added", "reaction_removed"):
        logger.info("Slack %s: %s by %s", event_type, event.get("reaction"), event.get("user"))

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="slack",
                event_type=event_type,
                payload={
                    "event_id": payload.get("event_id"),
                    "team_id": team_id,
                    "api_app_id": api_app_id,
                    "channel": event.get("channel"),
                    "user": event.get("user"),
                    "text": event.get("text", "")[:500],
                    "ts": event.get("ts"),
                    "thread_ts": event.get("thread_ts"),
                },
                delivery_id=payload.get("event_id"),
            )
            await event_db.commit()
    except Exception:
        logger.warning("Slack event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "event": event_type}
