"""ClickUp webhook handler — receives task and comment lifecycle events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clickup", tags=["clickup"])


def _verify_clickup_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify ClickUp webhook signature (HMAC-SHA256).

    ClickUp sends the signature in the X-Signature header as a hex digest.
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
async def clickup_webhook(request: Request):
    """Handle ClickUp webhook events (task lifecycle, comments)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.CLICKUP_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-signature", "")
        if not _verify_clickup_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # ClickUp webhook handshake: respond to challenge
    if "challenge" in event:
        return {"challenge": event["challenge"]}

    event_type = event.get("event", "unknown")
    task = event.get("task", {})

    logger.info(
        "ClickUp webhook: event=%s task_id=%s task_name=%s",
        event_type,
        task.get("id", "unknown"),
        task.get("name", "unknown"),
    )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="clickup",
                event_type=event_type,
                payload={
                    "event": event_type,
                    "task_id": task.get("id"),
                    "task_name": task.get("name"),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("ClickUp event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "event": event_type}
